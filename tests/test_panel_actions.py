"""Pruebas de formularios, acciones y permisos de escritura del panel."""
from datetime import date
from decimal import Decimal
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from finance.budgets.models import Budget, BudgetLine
from finance.expenses.models import Expense
from finance.investments.models import Investment, InvestmentMovement
from finance.security.models import UserTenantRole
from tenants.models import Tenant

User = get_user_model()


class ActionsBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.t1 = Tenant.objects.create(name='Empresa Uno', slug='uno')
        cls.t2 = Tenant.objects.create(name='Empresa Dos', slug='dos')
        cls.admin = User.objects.create_superuser('admin', 'a@example.com', 'pass12345')
        cls.manager = User.objects.create_user('gerente', password='pass12345')
        cls.viewer = User.objects.create_user('lector', password='pass12345')
        UserTenantRole.objects.create(tenant=cls.t1, user=cls.manager, role='manager')
        UserTenantRole.objects.create(tenant=cls.t1, user=cls.viewer, role='viewer')

    def budget(self, tenant=None, status='draft', **kw):
        defaults = dict(tenant=tenant or self.t1, name='Presupuesto', fiscal_year=2026, status=status,
                        period_start=date(2026, 1, 1), period_end=date(2026, 12, 31), currency='USD')
        defaults.update(kw)
        return Budget.objects.create(**defaults)

    def investment(self, tenant=None, **kw):
        defaults = dict(tenant=tenant or self.t1, name='Deposito', initial_amount=Decimal('1000.00'),
                        start_date=date(2026, 1, 1), currency='USD')
        defaults.update(kw)
        return Investment.objects.create(**defaults)

    def expense(self, tenant=None, status='pending', **kw):
        defaults = dict(tenant=tenant or self.t1, description='Gasto', category='travel', amount=Decimal('50.00'),
                        currency='USD', expense_date=date(2026, 3, 1), status=status)
        defaults.update(kw)
        return Expense.objects.create(**defaults)


class BudgetFormTests(ActionsBase):
    def payload(self, **overrides):
        data = {
            'name': 'Nuevo', 'fiscal_year': 2026, 'period_start': '2026-01-01', 'period_end': '2026-12-31',
            'currency': 'USD', 'notes': '',
            'lines-TOTAL_FORMS': 3, 'lines-INITIAL_FORMS': 0, 'lines-MIN_NUM_FORMS': 0, 'lines-MAX_NUM_FORMS': 1000,
            'lines-0-category': 'rent', 'lines-0-planned_amount': '1200.00', 'lines-0-notes': '',
            'lines-1-category': 'travel', 'lines-1-planned_amount': '300.50', 'lines-1-notes': '',
            'lines-2-category': '', 'lines-2-planned_amount': '', 'lines-2-notes': '',
        }
        data.update(overrides)
        return data

    def test_manager_creates_budget_with_lines_ignoring_blank_rows(self):
        self.client.force_login(self.manager)
        response = self.client.post(reverse('panel:budget-create'), self.payload())
        budget = Budget.objects.get(name='Nuevo')
        self.assertRedirects(response, reverse('panel:budget-detail', args=[budget.pk]))
        self.assertEqual(budget.tenant, self.t1)
        self.assertEqual(budget.created_by, self.manager)
        self.assertEqual(budget.status, 'draft')
        self.assertEqual(budget.lines.count(), 2)

    def test_viewer_cannot_open_or_submit_create_form(self):
        self.client.force_login(self.viewer)
        self.assertEqual(self.client.get(reverse('panel:budget-create')).status_code, 403)
        self.assertEqual(self.client.post(reverse('panel:budget-create'), self.payload()).status_code, 403)
        self.assertFalse(Budget.objects.exists())

    def test_invalid_dates_and_duplicates_are_rejected(self):
        self.budget(name='Nuevo')
        self.client.force_login(self.manager)
        response = self.client.post(reverse('panel:budget-create'),
                                    self.payload(period_start='2026-06-01', period_end='2026-01-01'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'anterior al inicio')
        self.assertContains(response, 'Ya existe un presupuesto')
        self.assertEqual(Budget.objects.count(), 1)

    def test_duplicate_category_in_same_budget_is_rejected(self):
        self.client.force_login(self.manager)
        data = self.payload(**{'lines-1-category': 'rent'})
        self.assertEqual(self.client.post(reverse('panel:budget-create'), data).status_code, 200)
        self.assertFalse(Budget.objects.exists())

    def test_non_positive_line_amount_is_rejected(self):
        self.client.force_login(self.manager)
        data = self.payload(**{'lines-0-planned_amount': '0'})
        self.assertEqual(self.client.post(reverse('panel:budget-create'), data).status_code, 200)
        self.assertFalse(Budget.objects.exists())

    def test_edit_only_while_draft(self):
        approved = self.budget(name='Aprobado', status='approved')
        self.client.force_login(self.manager)
        response = self.client.get(reverse('panel:budget-edit', args=[approved.pk]))
        self.assertRedirects(response, reverse('panel:budget-detail', args=[approved.pk]))

    def test_edit_draft_updates_and_can_remove_line(self):
        draft = self.budget(name='Borrador')
        line = BudgetLine.objects.create(budget=draft, category='rent', planned_amount=Decimal('100.00'))
        self.client.force_login(self.manager)
        data = {
            'name': 'Renombrado', 'fiscal_year': 2026, 'period_start': '2026-01-01', 'period_end': '2026-12-31',
            'currency': 'USD', 'notes': '',
            'lines-TOTAL_FORMS': 1, 'lines-INITIAL_FORMS': 1, 'lines-MIN_NUM_FORMS': 0, 'lines-MAX_NUM_FORMS': 1000,
            'lines-0-id': line.pk, 'lines-0-budget': draft.pk, 'lines-0-category': 'rent',
            'lines-0-planned_amount': '100.00', 'lines-0-notes': '', 'lines-0-DELETE': 'on',
        }
        self.client.post(reverse('panel:budget-edit', args=[draft.pk]), data)
        draft.refresh_from_db()
        self.assertEqual(draft.name, 'Renombrado')
        self.assertEqual(draft.lines.count(), 0)


class BudgetActionTests(ActionsBase):
    def act(self, budget, action, user=None):
        self.client.force_login(user or self.manager)
        return self.client.post(reverse('panel:budget-action', args=[budget.pk, action]))

    def test_approve_requires_lines_then_works_once(self):
        budget = self.budget()
        self.act(budget, 'approve')
        budget.refresh_from_db()
        self.assertEqual(budget.status, 'draft')  # sin categorias no se aprueba
        BudgetLine.objects.create(budget=budget, category='rent', planned_amount=Decimal('10.00'))
        self.act(budget, 'approve')
        budget.refresh_from_db()
        self.assertEqual((budget.status, budget.approved_by), ('approved', self.manager))
        self.assertIsNotNone(budget.approved_at)

    def test_close_only_from_approved(self):
        draft = self.budget(name='A')
        self.act(draft, 'close')
        draft.refresh_from_db()
        self.assertEqual(draft.status, 'draft')
        approved = self.budget(name='B', status='approved')
        self.act(approved, 'close')
        approved.refresh_from_db()
        self.assertEqual(approved.status, 'closed')

    def test_delete_only_drafts(self):
        approved = self.budget(name='B', status='approved')
        self.act(approved, 'delete')
        self.assertTrue(Budget.objects.filter(pk=approved.pk).exists())
        draft = self.budget(name='A')
        self.assertRedirects(self.act(draft, 'delete'), reverse('panel:budgets'))
        self.assertFalse(Budget.objects.filter(pk=draft.pk).exists())

    def test_viewer_and_foreign_users_cannot_act(self):
        budget = self.budget()
        BudgetLine.objects.create(budget=budget, category='rent', planned_amount=Decimal('10.00'))
        self.assertEqual(self.act(budget, 'approve', user=self.viewer).status_code, 403)
        foreign = self.budget(tenant=self.t2, name='Ajeno')
        self.assertEqual(self.act(foreign, 'delete').status_code, 404)
        budget.refresh_from_db()
        self.assertEqual(budget.status, 'draft')

    def test_actions_reject_get(self):
        budget = self.budget()
        self.client.force_login(self.manager)
        self.assertEqual(self.client.get(reverse('panel:budget-action', args=[budget.pk, 'delete'])).status_code, 405)


class ExpenseTests(ActionsBase):
    def test_create_expense_is_pending_and_owned_by_tenant(self):
        self.client.force_login(self.manager)
        response = self.client.post(reverse('panel:expense-create'), {
            'description': 'Taxi', 'category': 'travel', 'amount': '25.50', 'currency': 'USD',
            'expense_date': '2026-05-02', 'notes': ''})
        self.assertRedirects(response, reverse('panel:expenses'))
        expense = Expense.objects.get(description='Taxi')
        self.assertEqual((expense.tenant, expense.status, expense.submitted_by), (self.t1, 'pending', self.manager))

    def test_new_forms_default_to_usd_not_the_model_default(self):
        self.client.force_login(self.manager)
        for name in ('panel:expense-create', 'panel:budget-create', 'panel:investment-create'):
            form = self.client.get(reverse(name)).context['form']
            self.assertEqual(form['currency'].value(), 'USD', name)

    def test_amount_must_be_positive(self):
        self.client.force_login(self.manager)
        response = self.client.post(reverse('panel:expense-create'), {
            'description': 'Taxi', 'category': 'travel', 'amount': '-5', 'currency': 'USD',
            'expense_date': '2026-05-02'})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Expense.objects.exists())

    def test_status_flow(self):
        expense = self.expense()
        self.client.force_login(self.manager)
        url = lambda action: reverse('panel:expense-action', args=[expense.pk, action])  # noqa: E731
        self.client.post(url('pay'))  # no se puede pagar un gasto pendiente
        expense.refresh_from_db()
        self.assertEqual(expense.status, 'pending')
        self.client.post(url('approve'))
        expense.refresh_from_db()
        self.assertEqual((expense.status, expense.approved_by), ('approved', self.manager))
        self.client.post(url('pay'))
        expense.refresh_from_db()
        self.assertEqual(expense.status, 'paid')
        self.client.post(url('delete'))  # un gasto pagado no se elimina
        self.assertTrue(Expense.objects.filter(pk=expense.pk).exists())

    def test_viewer_cannot_change_or_create(self):
        expense = self.expense()
        self.client.force_login(self.viewer)
        approve_url = reverse('panel:expense-action', args=[expense.pk, 'approve'])
        self.assertEqual(self.client.post(approve_url).status_code, 403)
        self.assertEqual(self.client.get(reverse('panel:expense-create')).status_code, 403)
        self.assertContains(self.client.get(reverse('panel:expenses')), 'Solo lectura')

    def test_next_redirect_only_internal(self):
        expense = self.expense()
        self.client.force_login(self.manager)
        response = self.client.post(reverse('panel:expense-action', args=[expense.pk, 'approve']),
                                    {'next': 'https://evil.example.com/'})
        self.assertRedirects(response, reverse('panel:expenses'))

    def test_filters(self):
        self.expense(description='Pendiente uno')
        self.expense(description='Pagado uno', status='paid')
        self.client.force_login(self.manager)
        response = self.client.get(reverse('panel:expenses'), {'status': 'paid'})
        self.assertContains(response, 'Pagado uno')
        self.assertNotContains(response, 'Pendiente uno')


class InvestmentActionTests(ActionsBase):
    def test_create_investment(self):
        self.client.force_login(self.manager)
        response = self.client.post(reverse('panel:investment-create'), {
            'name': 'Bono', 'asset_type': 'bond', 'institution': 'Banco', 'currency': 'USD',
            'initial_amount': '2500.00', 'start_date': '2026-02-01', 'maturity_date': '2027-02-01',
            'expected_return_rate': '5', 'status': 'active', 'notes': ''})
        investment = Investment.objects.get(name='Bono')
        self.assertRedirects(response, reverse('panel:investment-detail', args=[investment.pk]))
        self.assertEqual(investment.tenant, self.t1)

    def test_maturity_before_start_is_rejected(self):
        self.client.force_login(self.manager)
        response = self.client.post(reverse('panel:investment-create'), {
            'name': 'Bono', 'asset_type': 'bond', 'currency': 'USD', 'initial_amount': '10',
            'start_date': '2026-02-01', 'maturity_date': '2026-01-01', 'status': 'active'})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Investment.objects.exists())

    def test_add_and_delete_movement_updates_balance(self):
        investment = self.investment()
        self.client.force_login(self.manager)
        self.client.post(reverse('panel:movement-add', args=[investment.pk]),
                         {'movement_type': 'return', 'amount': '100.00', 'movement_date': '2026-03-01', 'notes': ''})
        movement = InvestmentMovement.objects.get(investment=investment)
        response = self.client.get(reverse('panel:investment-detail', args=[investment.pk]))
        self.assertEqual(response.context['summary']['current_balance'], Decimal('1100.00'))
        self.client.post(reverse('panel:movement-delete', args=[investment.pk, movement.pk]))
        self.assertFalse(InvestmentMovement.objects.exists())

    def test_invalid_movement_is_not_saved(self):
        investment = self.investment()
        self.client.force_login(self.manager)
        self.client.post(reverse('panel:movement-add', args=[investment.pk]),
                         {'movement_type': 'fee', 'amount': '0', 'movement_date': '2026-03-01'})
        self.assertFalse(InvestmentMovement.objects.exists())

    def test_viewer_cannot_write_and_foreign_is_404(self):
        investment = self.investment()
        self.client.force_login(self.viewer)
        self.assertEqual(self.client.post(reverse('panel:movement-add', args=[investment.pk]), {}).status_code, 403)
        self.assertEqual(self.client.post(reverse('panel:investment-delete', args=[investment.pk])).status_code, 403)
        self.assertTrue(Investment.objects.filter(pk=investment.pk).exists())
        foreign = self.investment(tenant=self.t2, name='Ajena')
        self.client.force_login(self.manager)
        self.assertEqual(self.client.post(reverse('panel:investment-delete', args=[foreign.pk])).status_code, 404)

    def test_delete_investment_removes_movements(self):
        investment = self.investment()
        InvestmentMovement.objects.create(investment=investment, movement_type='return', amount=Decimal('5'),
                                          movement_date=date(2026, 2, 1))
        self.client.force_login(self.manager)
        self.assertRedirects(self.client.post(reverse('panel:investment-delete', args=[investment.pk])),
                             reverse('panel:investments'))
        self.assertFalse(InvestmentMovement.objects.exists())


class ChartDataAndSeedTests(ActionsBase):
    def test_home_embeds_chart_data(self):
        budget = self.budget(status='approved')
        BudgetLine.objects.create(budget=budget, category='travel', planned_amount=Decimal('100.00'))
        self.expense(status='paid', amount=Decimal('150.00'))
        self.investment()
        self.client.force_login(self.manager)
        response = self.client.get(reverse('panel:home'))
        self.assertContains(response, 'id="chart-execution"')
        self.assertContains(response, 'id="chart-monthly"')
        self.assertEqual(response.context['chart_execution']['spent'], [150.0])
        self.assertEqual(response.context['chart_monthly']['values'][2], 150.0)  # marzo
        self.assertIn('USD', response.context['chart_portfolio'])

    def test_investment_timeline_is_cumulative(self):
        investment = self.investment()
        InvestmentMovement.objects.create(investment=investment, movement_type='return', amount=Decimal('100'),
                                          movement_date=date(2026, 2, 1))
        InvestmentMovement.objects.create(investment=investment, movement_type='fee', amount=Decimal('30'),
                                          movement_date=date(2026, 3, 1))
        self.client.force_login(self.manager)
        timeline = self.client.get(reverse('panel:investment-detail', args=[investment.pk])).context['chart_timeline']
        self.assertEqual(timeline['values'], [1000.0, 1100.0, 1070.0])

    def test_seed_demo_is_idempotent_and_never_creates_future_expenses(self):
        out = StringIO()
        call_command('seed_demo', stdout=out)
        tenant = Tenant.objects.get(slug='empresa-demo')
        self.assertEqual(Investment.objects.filter(tenant=tenant).count(), 3)
        self.assertEqual(Budget.objects.filter(tenant=tenant).count(), 2)
        from django.utils import timezone
        self.assertFalse(Expense.objects.filter(tenant=tenant, expense_date__gt=timezone.localdate()).exists())
        call_command('seed_demo', stdout=out)
        self.assertEqual(Tenant.objects.filter(slug='empresa-demo').count(), 1)
        call_command('seed_demo', '--reset', stdout=out)
        self.assertEqual(Investment.objects.count(), 3)
