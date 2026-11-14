"""Pruebas de los modulos de gestion gerencial: security, budgets e investments."""
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model

from rest_framework.test import APIClient, APITestCase

from finance.expenses.models import Expense
from finance.security.models import UserTenantRole
from tenants.models import Tenant

User = get_user_model()

BASE = '/api/finance'


class ManagementTestBase(APITestCase):
    """Dos empresas, un superusuario, un gerente y un lector de la empresa uno."""

    @classmethod
    def setUpTestData(cls):
        cls.tenant1 = Tenant.objects.create(name='Empresa Uno', slug='uno')
        cls.tenant2 = Tenant.objects.create(name='Empresa Dos', slug='dos')
        cls.admin = User.objects.create_superuser('admin', 'a@example.com', 'pass12345')
        cls.staff = User.objects.create_user('staff', password='pass12345', is_staff=True)
        cls.manager = User.objects.create_user('gerente', password='pass12345')
        cls.viewer = User.objects.create_user('lector', password='pass12345')
        cls.outsider = User.objects.create_user('sin_rol', password='pass12345')
        UserTenantRole.objects.create(tenant=cls.tenant1, user=cls.manager, role='manager')
        UserTenantRole.objects.create(tenant=cls.tenant1, user=cls.viewer, role='viewer')

    def client_for(self, user):
        client = APIClient()
        if user is not None:
            client.force_authenticate(user)
        return client

    def budget_payload(self, **overrides):
        data = {
            'tenant': self.tenant1.id,
            'name': 'Presupuesto 2026',
            'fiscal_year': 2026,
            'period_start': '2026-01-01',
            'period_end': '2026-12-31',
            'currency': 'USD',
        }
        data.update(overrides)
        return data

    def investment_payload(self, **overrides):
        data = {
            'tenant': self.tenant1.id,
            'name': 'Deposito a plazo',
            'asset_type': 'term_deposit',
            'initial_amount': '5000.00',
            'start_date': '2026-01-15',
            'currency': 'USD',
        }
        data.update(overrides)
        return data


class SecurityRolesTests(ManagementTestBase):
    url = f'{BASE}/security/roles/'

    def test_anonymous_is_rejected(self):
        self.assertIn(self.client_for(None).get(self.url).status_code, (401, 403))

    def test_non_staff_cannot_manage_roles(self):
        self.assertEqual(self.client_for(self.manager).get(self.url).status_code, 403)

    def test_staff_can_assign_role_and_records_assigner(self):
        response = self.client_for(self.staff).post(
            self.url, {'tenant': self.tenant2.id, 'user': self.outsider.id, 'role': 'analyst'}, format='json'
        )
        self.assertEqual(response.status_code, 201)
        role = UserTenantRole.objects.get(tenant=self.tenant2, user=self.outsider)
        self.assertEqual(role.assigned_by, self.staff)

    def test_mine_returns_only_own_active_roles(self):
        response = self.client_for(self.manager).get(f'{self.url}mine/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['role'], 'manager')

    def test_mine_ignores_inactive_roles(self):
        UserTenantRole.objects.filter(user=self.viewer).update(is_active=False)
        response = self.client_for(self.viewer).get(f'{self.url}mine/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 0)


class BudgetTests(ManagementTestBase):
    url = f'{BASE}/budgets/budgets/'
    lines_url = f'{BASE}/budgets/lines/'

    def create_budget(self, user=None, **overrides):
        return self.client_for(user or self.manager).post(
            self.url, self.budget_payload(**overrides), format='json'
        )

    def test_manager_creates_budget_in_own_tenant(self):
        response = self.create_budget()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['status'], 'draft')

    def test_manager_cannot_create_in_other_tenant(self):
        self.assertEqual(self.create_budget(tenant=self.tenant2.id).status_code, 403)

    def test_viewer_cannot_write_but_can_read(self):
        self.assertEqual(self.create_budget(user=self.viewer).status_code, 403)
        self.create_budget()
        self.assertEqual(self.client_for(self.viewer).get(self.url).status_code, 200)

    def test_user_without_role_cannot_read_or_write(self):
        self.assertEqual(self.client_for(self.outsider).get(self.url).status_code, 403)
        self.assertEqual(self.create_budget(user=self.outsider).status_code, 403)

    def test_listing_only_shows_own_tenant_budgets(self):
        self.create_budget()
        self.create_budget(user=self.admin, tenant=self.tenant2.id, name='Ajeno')
        response = self.client_for(self.manager).get(self.url)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(self.client_for(self.admin).get(self.url).data['count'], 2)

    def test_foreign_budget_is_not_found(self):
        other = self.create_budget(user=self.admin, tenant=self.tenant2.id, name='Ajeno').data['id']
        self.assertEqual(self.client_for(self.manager).get(f'{self.url}{other}/').status_code, 404)

    def test_duplicate_name_and_year_is_rejected(self):
        self.create_budget()
        self.assertEqual(self.create_budget().status_code, 400)

    def test_approve_flow(self):
        budget_id = self.create_budget().data['id']
        manager = self.client_for(self.manager)
        response = manager.post(f'{self.url}{budget_id}/approve/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['status'], 'approved')
        self.assertEqual(response.data['approved_by'], self.manager.id)
        self.assertEqual(manager.post(f'{self.url}{budget_id}/approve/').status_code, 400)

    def test_viewer_cannot_approve(self):
        budget_id = self.create_budget().data['id']
        self.assertEqual(self.client_for(self.viewer).post(f'{self.url}{budget_id}/approve/').status_code, 403)

    def test_line_cannot_be_added_to_foreign_budget(self):
        other = self.create_budget(user=self.admin, tenant=self.tenant2.id, name='Ajeno').data['id']
        response = self.client_for(self.manager).post(
            self.lines_url, {'budget': other, 'category': 'travel', 'planned_amount': '100.00'}, format='json'
        )
        self.assertIn(response.status_code, (400, 403, 404))
        self.assertEqual(self.client_for(self.admin).get(f'{self.lines_url}?budget={other}').data['count'], 0)

    def test_execution_compares_plan_against_real_spending(self):
        budget_id = self.create_budget().data['id']
        manager = self.client_for(self.manager)
        for category, amount in (('travel', '1000.00'), ('rent', '500.00')):
            self.assertEqual(
                manager.post(self.lines_url, {'budget': budget_id, 'category': category, 'planned_amount': amount},
                             format='json').status_code,
                201,
            )

        def expense(category, amount, status='approved', currency='USD', tenant=None, when=date(2026, 3, 10)):
            Expense.objects.create(
                tenant=tenant or self.tenant1, description='x', category=category, amount=Decimal(amount),
                currency=currency, expense_date=when, status=status,
            )

        expense('travel', '400.00')
        expense('travel', '700.00', status='paid')          # supera lo planificado
        expense('travel', '999.00', status='pending')        # no cuenta
        expense('travel', '999.00', currency='UGX')          # otra moneda, no cuenta
        expense('travel', '999.00', tenant=self.tenant2)     # otra empresa, no cuenta
        expense('travel', '999.00', when=date(2025, 12, 31))  # fuera del periodo, no cuenta
        expense('fuel', '50.00')                             # sin presupuestar

        data = manager.get(f'{self.url}{budget_id}/execution/').data
        lines = {line['category']: line for line in data['lines']}
        self.assertEqual(Decimal(str(data['total_planned'])), Decimal('1500.00'))
        self.assertEqual(Decimal(str(data['total_spent'])), Decimal('1150.00'))
        self.assertEqual(Decimal(str(data['total_remaining'])), Decimal('350.00'))
        self.assertTrue(lines['travel']['over_budget'])
        self.assertFalse(lines['rent']['over_budget'])
        self.assertEqual(Decimal(str(lines['travel']['spent'])), Decimal('1100.00'))
        self.assertEqual(Decimal(str(data['unbudgeted_spending']['fuel'])), Decimal('50.00'))


class InvestmentTests(ManagementTestBase):
    url = f'{BASE}/investments/investments/'
    movements_url = f'{BASE}/investments/movements/'

    def create_investment(self, user=None, **overrides):
        return self.client_for(user or self.manager).post(
            self.url, self.investment_payload(**overrides), format='json'
        )

    def add_movement(self, investment_id, movement_type, amount, user=None):
        return self.client_for(user or self.manager).post(
            self.movements_url,
            {'investment': investment_id, 'movement_type': movement_type, 'amount': amount,
             'movement_date': '2026-03-01'},
            format='json',
        )

    def test_manager_creates_investment_in_own_tenant(self):
        response = self.create_investment()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['status'], 'active')

    def test_write_permissions_by_tenant_and_role(self):
        self.assertEqual(self.create_investment(tenant=self.tenant2.id).status_code, 403)
        self.assertEqual(self.create_investment(user=self.viewer).status_code, 403)
        self.assertEqual(self.create_investment(user=self.outsider).status_code, 403)

    def test_listing_is_scoped_to_tenant(self):
        self.create_investment()
        self.create_investment(user=self.admin, tenant=self.tenant2.id, name='Ajena')
        self.assertEqual(self.client_for(self.manager).get(self.url).data['count'], 1)

    def test_movement_on_foreign_investment_is_forbidden(self):
        foreign = self.create_investment(user=self.admin, tenant=self.tenant2.id, name='Ajena').data['id']
        self.assertEqual(self.add_movement(foreign, 'fee', '1.00').status_code, 403)

    def test_summary_computes_balance(self):
        investment_id = self.create_investment().data['id']
        for movement_type, amount in (
            ('contribution', '1000.00'), ('return', '250.00'), ('withdrawal', '100.00'), ('fee', '20.00'),
        ):
            self.assertEqual(self.add_movement(investment_id, movement_type, amount).status_code, 201)
        data = self.client_for(self.manager).get(f'{self.url}{investment_id}/summary/').data
        self.assertEqual(Decimal(str(data['invested_capital'])), Decimal('6000.00'))
        self.assertEqual(Decimal(str(data['current_balance'])), Decimal('6130.00'))
        self.assertEqual(Decimal(str(data['net_return'])), Decimal('230.00'))

    def test_portfolio_groups_active_investments_by_currency(self):
        usd = self.create_investment().data['id']
        self.create_investment(name='En euros', currency='EUR', initial_amount='1000.00')
        self.create_investment(name='Vendida', status='sold')
        self.add_movement(usd, 'return', '100.00')
        data = self.client_for(self.manager).get(f'{self.url}portfolio/').data
        self.assertEqual(data['USD']['investments'], 1)
        self.assertEqual(Decimal(str(data['USD']['current_balance'])), Decimal('5100.00'))
        self.assertEqual(data['EUR']['investments'], 1)

    def test_portfolio_does_not_include_other_tenants(self):
        self.create_investment(user=self.admin, tenant=self.tenant2.id, name='Ajena')
        self.assertEqual(self.client_for(self.manager).get(f'{self.url}portfolio/').data, {})
