"""Panel web gerencial."""
from datetime import date
from decimal import Decimal

from finance.expenses.models import Expense

from .test_management_modules import ManagementTestBase


class PanelTests(ManagementTestBase):

    def login(self, user):
        self.client.force_login(user)

    def test_requires_login(self):
        response = self.client.get('/panel/')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/panel/login/', response['Location'])

    def test_root_redirects_to_panel(self):
        self.assertRedirects(self.client.get('/'), '/panel/', fetch_redirect_response=False)

    def test_login_page_renders(self):
        self.assertContains(self.client.get('/panel/login/'), 'Iniciar sesión')

    def test_user_without_companies_sees_notice(self):
        self.login(self.outsider)
        self.assertContains(self.client.get('/panel/'), 'Sin empresas asignadas')

    def test_dashboard_shows_own_company_only(self):
        Expense.objects.create(tenant=self.tenant1, description='x', category='rent', amount=Decimal('123.45'),
                               currency='USD', expense_date=date.today(), status='approved')
        self.login(self.viewer)
        response = self.client.get(f'/panel/?tenant={self.tenant2.id}')
        self.assertContains(response, 'Empresa Uno')
        self.assertNotContains(response, 'Empresa Dos')
        self.assertContains(response, '123')

    def test_invalid_dates_show_error_instead_of_crashing(self):
        self.login(self.manager)
        response = self.client.get('/panel/?start_date=2026-05-01&end_date=2026-01-01')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'No puede ser anterior')

    def test_superuser_sees_all_companies(self):
        self.login(self.admin)
        response = self.client.get('/panel/')
        self.assertContains(response, 'Empresa Uno')
        self.assertContains(response, 'Empresa Dos')

    def test_progress_bar_widths_are_valid_css(self):
        from finance.budgets.models import Budget, BudgetLine
        budget = Budget.objects.create(tenant=self.tenant1, name='P', fiscal_year=2026, status='approved',
                                       currency='USD', period_start=date(2026, 1, 1), period_end=date(2026, 12, 31))
        BudgetLine.objects.create(budget=budget, category='rent', planned_amount=Decimal('300'))
        Expense.objects.create(tenant=self.tenant1, description='x', category='rent', amount=Decimal('100'),
                               currency='USD', expense_date=date(2026, 2, 1), status='approved')
        self.login(self.manager)
        response = self.client.get('/panel/?start_date=2026-01-01&end_date=2026-12-31')
        # Con LANGUAGE_CODE=es un float se mostraria '33,33': el CSS necesita punto decimal.
        self.assertContains(response, 'width:33.33')
        self.assertContains(response, 'Alquiler')

    def test_shows_latest_bcv_rate(self):
        from finance.fx.models import ExchangeRate
        for day, rate in ((1, '400'), (20, '420.5')):
            ExchangeRate.objects.create(tenant=self.tenant1, from_currency='USD', to_currency='VES',
                                        rate=Decimal(rate), rate_date=date(2026, 11, day), source='bcv')
        self.login(self.manager)
        response = self.client.get('/panel/')
        self.assertContains(response, '420,5000')
        self.assertContains(response, '(BCV, 20/11/2026)')
