"""Pruebas del panel web: login, seleccion de empresa y acceso por rol."""
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from finance.budgets.models import Budget, BudgetLine
from finance.expenses.models import Expense
from finance.investments.models import Investment, InvestmentMovement
from finance.security.models import UserTenantRole
from tenants.models import Tenant

User = get_user_model()


class PanelTestBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.t1 = Tenant.objects.create(name='Empresa Uno', slug='uno')
        cls.t2 = Tenant.objects.create(name='Empresa Dos', slug='dos')
        cls.admin = User.objects.create_superuser('admin', 'a@example.com', 'pass12345')
        cls.viewer = User.objects.create_user('lector', password='pass12345')
        cls.norole = User.objects.create_user('sin_rol', password='pass12345')
        UserTenantRole.objects.create(tenant=cls.t1, user=cls.viewer, role='viewer')

        cls.b1 = Budget.objects.create(
            tenant=cls.t1, name='Presupuesto Uno', fiscal_year=2026, status='approved',
            period_start=date(2026, 1, 1), period_end=date(2026, 12, 31), currency='USD')
        BudgetLine.objects.create(budget=cls.b1, category='travel', planned_amount=Decimal('1000.00'))
        Expense.objects.create(
            tenant=cls.t1, description='Vuelo', category='travel', amount=Decimal('250.00'),
            currency='USD', expense_date=date(2026, 3, 1), status='approved')
        cls.b2 = Budget.objects.create(
            tenant=cls.t2, name='Presupuesto Dos', fiscal_year=2026,
            period_start=date(2026, 1, 1), period_end=date(2026, 12, 31), currency='USD')

        cls.i1 = Investment.objects.create(
            tenant=cls.t1, name='Deposito Uno', initial_amount=Decimal('5000.00'),
            start_date=date(2026, 1, 15), currency='USD', asset_type='term_deposit')
        InvestmentMovement.objects.create(
            investment=cls.i1, movement_type='return', amount=Decimal('250.00'), movement_date=date(2026, 3, 1))
        cls.i2 = Investment.objects.create(
            tenant=cls.t2, name='Deposito Dos', initial_amount=Decimal('900.00'),
            start_date=date(2026, 1, 15), currency='USD')


class PanelAuthTests(PanelTestBase):
    def test_anonymous_is_redirected_to_login(self):
        for name in ('panel:home', 'panel:budgets', 'panel:investments'):
            response = self.client.get(reverse(name))
            self.assertRedirects(response, f"{reverse('panel:login')}?next={reverse(name)}")

    def test_login_page_renders_and_login_works(self):
        self.assertEqual(self.client.get(reverse('panel:login')).status_code, 200)
        response = self.client.post(reverse('panel:login'), {'username': 'lector', 'password': 'pass12345'})
        self.assertRedirects(response, reverse('panel:home'))

    def test_logout_ends_session(self):
        self.client.force_login(self.viewer)
        self.assertEqual(self.client.get(reverse('panel:home')).status_code, 200)
        self.client.post(reverse('panel:logout'))
        self.assertEqual(self.client.get(reverse('panel:home')).status_code, 302)


class PanelAccessTests(PanelTestBase):
    def test_viewer_sees_only_own_tenant(self):
        self.client.force_login(self.viewer)
        response = self.client.get(reverse('panel:home'))
        self.assertContains(response, 'Empresa Uno')
        self.assertNotContains(response, 'Empresa Dos')
        self.assertEqual(response.context['tenant'], self.t1)

    def test_viewer_cannot_select_foreign_tenant(self):
        self.client.force_login(self.viewer)
        response = self.client.get(reverse('panel:budgets'), {'tenant': self.t2.id})
        self.assertEqual(response.context['tenant'], self.t1)
        self.assertContains(response, 'Presupuesto Uno')
        self.assertNotContains(response, 'Presupuesto Dos')

    def test_foreign_detail_pages_are_404(self):
        self.client.force_login(self.viewer)
        self.assertEqual(self.client.get(reverse('panel:budget-detail', args=[self.b2.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse('panel:investment-detail', args=[self.i2.pk])).status_code, 404)

    def test_user_without_role_sees_empty_state(self):
        self.client.force_login(self.norole)
        for name in ('panel:home', 'panel:budgets', 'panel:investments'):
            response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, 'Sin empresas asignadas')

    def test_superuser_can_switch_between_tenants(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('panel:budgets'), {'tenant': self.t2.id})
        self.assertEqual(response.context['tenant'], self.t2)
        self.assertContains(response, 'Presupuesto Dos')
        # La seleccion queda guardada en la sesion.
        self.assertEqual(self.client.get(reverse('panel:budgets')).context['tenant'], self.t2)
        self.assertEqual(self.client.get(reverse('panel:budget-detail', args=[self.b2.pk])).status_code, 200)

    def test_inactive_role_gives_no_access(self):
        UserTenantRole.objects.filter(user=self.viewer).update(is_active=False)
        self.client.force_login(self.viewer)
        self.assertContains(self.client.get(reverse('panel:home')), 'Sin empresas asignadas')


class PanelContentTests(PanelTestBase):
    def setUp(self):
        self.client.force_login(self.viewer)

    def test_home_shows_execution_and_portfolio(self):
        response = self.client.get(reverse('panel:home'))
        self.assertContains(response, 'Presupuesto Uno')
        self.assertContains(response, 'Viajes')
        self.assertContains(response, '5,250.00')  # saldo del portafolio

    def test_budget_detail_numbers(self):
        response = self.client.get(reverse('panel:budget-detail', args=[self.b1.pk]))
        execution = response.context['execution']
        self.assertEqual(execution['total_planned'], Decimal('1000.00'))
        self.assertEqual(execution['total_spent'], Decimal('250.00'))
        self.assertEqual(execution['total_remaining'], Decimal('750.00'))
        self.assertContains(response, '25%')

    def test_budget_detail_flags_overspending_and_unbudgeted(self):
        Expense.objects.create(
            tenant=self.t1, description='Gasolina', category='fuel', amount=Decimal('40.00'),
            currency='USD', expense_date=date(2026, 4, 1), status='paid')
        Expense.objects.create(
            tenant=self.t1, description='Otro vuelo', category='travel', amount=Decimal('900.00'),
            currency='USD', expense_date=date(2026, 5, 1), status='paid')
        response = self.client.get(reverse('panel:budget-detail', args=[self.b1.pk]))
        self.assertContains(response, 'excedido')
        self.assertContains(response, 'sin presupuestar')
        self.assertContains(response, 'Combustible')

    def test_investment_pages(self):
        listing = self.client.get(reverse('panel:investments'))
        self.assertContains(listing, 'Deposito Uno')
        self.assertNotContains(listing, 'Deposito Dos')
        detail = self.client.get(reverse('panel:investment-detail', args=[self.i1.pk]))
        self.assertEqual(detail.context['summary']['current_balance'], Decimal('5250.00'))
        self.assertContains(detail, 'Rendimiento')
