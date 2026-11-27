"""Reportes (resumen gerencial, balance) y nomina configurable por empresa."""
from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase

from finance.accounts.models import Account, JournalEntry, JournalLine
from finance.budgets.models import Budget, BudgetLine
from finance.expenses.models import Expense
from finance.payroll.config import PayrollConfigError, get_payroll_config, validate_payroll_config
from finance.payroll.models import EmployeePayrollProfile
from finance.payroll.services import PayrollService
from finance.reports.services import ReportService
from finance.statutory.models import StatutoryObligation
from tenants.models import Tenant, TenantSetting

from .test_management_modules import ManagementTestBase

REPORTS = '/api/finance/reports'


def post_entry(tenant, when, lines):
    entry = JournalEntry.objects.create(tenant=tenant, entry_date=when)
    for account, debit, credit in lines:
        JournalLine.objects.create(tenant=tenant, journal_entry=entry, account=account,
                                   debit_amount=Decimal(debit), credit_amount=Decimal(credit))
    return entry


class LedgerMixin:

    def make_ledger(self, tenant):
        acc = {
            'cash': Account.objects.create(tenant=tenant, code='1000', name='Caja', category='asset'),
            'loan': Account.objects.create(tenant=tenant, code='2000', name='Prestamo', category='liability'),
            'capital': Account.objects.create(tenant=tenant, code='3000', name='Capital', category='equity'),
            'sales': Account.objects.create(tenant=tenant, code='4000', name='Ventas', category='income'),
            'rent': Account.objects.create(tenant=tenant, code='5000', name='Alquiler', category='expense'),
        }
        post_entry(tenant, date(2026, 1, 2), [(acc['cash'], '1000', '0'), (acc['capital'], '0', '1000')])
        post_entry(tenant, date(2026, 1, 5), [(acc['cash'], '500', '0'), (acc['loan'], '0', '500')])
        post_entry(tenant, date(2026, 2, 1), [(acc['cash'], '800', '0'), (acc['sales'], '0', '800')])
        post_entry(tenant, date(2026, 2, 3), [(acc['rent'], '300', '0'), (acc['cash'], '0', '300')])
        void = post_entry(tenant, date(2026, 2, 4), [(acc['rent'], '999', '0'), (acc['cash'], '0', '999')])
        void.is_void = True
        void.save()
        return acc


class BalanceSheetTests(LedgerMixin, TestCase):

    def test_balance_sheet_balances_and_ignores_void_entries(self):
        tenant = Tenant.objects.create(name='T', slug='t')
        self.make_ledger(tenant)
        sheet = ReportService.get_balance_sheet(tenant, date(2026, 12, 31))
        self.assertEqual(sheet['total_assets'], Decimal('2000'))
        self.assertEqual(sheet['liabilities']['total'], Decimal('500'))
        self.assertEqual(sheet['equity']['total'], Decimal('1000'))
        self.assertEqual(sheet['current_earnings'], Decimal('500'))
        self.assertTrue(sheet['is_balanced'])

    def test_balance_sheet_respects_cutoff_date(self):
        tenant = Tenant.objects.create(name='T', slug='t')
        self.make_ledger(tenant)
        sheet = ReportService.get_balance_sheet(tenant, date(2026, 1, 31))
        self.assertEqual(sheet['total_assets'], Decimal('1500'))
        self.assertEqual(sheet['current_earnings'], Decimal('0'))
        self.assertTrue(sheet['is_balanced'])


class ReportAccessTests(LedgerMixin, ManagementTestBase):

    def test_reports_reject_other_companies(self):
        client = self.client_for(self.manager)
        for url in ('income-statement/?start_date=2026-01-01&end_date=2026-12-31', 'outstanding-invoices/',
                    'balance-sheet/', 'dashboard/', 'payroll-summary/?year=2026'):
            with self.subTest(url=url):
                response = client.get(f'{REPORTS}/{url}&tenant_id={self.tenant2.id}'.replace('/&', '/?'))
                self.assertEqual(response.status_code, 403)

    def test_unknown_tenant_looks_like_forbidden(self):
        response = self.client_for(self.manager).get(f'{REPORTS}/dashboard/?tenant_id=999999')
        self.assertEqual(response.status_code, 403)

    def test_invalid_dates_return_400(self):
        response = self.client_for(self.manager).get(
            f'{REPORTS}/income-statement/?tenant_id={self.tenant1.id}&start_date=ayer&end_date=2026-01-01')
        self.assertEqual(response.status_code, 400)
        response = self.client_for(self.manager).get(
            f'{REPORTS}/income-statement/?tenant_id={self.tenant1.id}&start_date=2026-02-01&end_date=2026-01-01')
        self.assertEqual(response.status_code, 400)

    def test_viewer_cannot_see_payroll_summary(self):
        response = self.client_for(self.viewer).get(f'{REPORTS}/payroll-summary/?tenant_id={self.tenant1.id}&year=2026')
        self.assertEqual(response.status_code, 403)

    def test_income_statement_for_own_company(self):
        self.make_ledger(self.tenant1)
        response = self.client_for(self.viewer).get(
            f'{REPORTS}/income-statement/?tenant_id={self.tenant1.id}&start_date=2026-01-01&end_date=2026-12-31')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['net_profit'], Decimal('500'))


class DashboardTests(LedgerMixin, ManagementTestBase):

    def test_dashboard_kpis_and_alerts(self):
        self.make_ledger(self.tenant1)
        budget = Budget.objects.create(
            tenant=self.tenant1, name='Operativo', fiscal_year=2026, status='approved', currency='USD',
            period_start=date(2026, 1, 1), period_end=date(2026, 12, 31),
        )
        BudgetLine.objects.create(budget=budget, category='rent', planned_amount=Decimal('1000'))
        Expense.objects.create(tenant=self.tenant1, description='Alquiler', category='rent', amount=Decimal('1200'),
                               currency='USD', expense_date=date(2026, 3, 1), status='approved')
        Expense.objects.create(tenant=self.tenant1, description='Pendiente', category='fuel', amount=Decimal('10'),
                               currency='USD', expense_date=date(2026, 3, 2), status='pending')
        Expense.objects.create(tenant=self.tenant2, description='Ajeno', category='rent', amount=Decimal('5000'),
                               currency='USD', expense_date=date(2026, 3, 1), status='approved')
        today = date(2026, 6, 1)
        StatutoryObligation.objects.create(tenant=self.tenant1, obligation_type='vat', period_month=4,
                                           period_year=2026, amount_due=Decimal('70'), due_date=today - timedelta(1))
        StatutoryObligation.objects.create(tenant=self.tenant1, obligation_type='paye', period_month=5,
                                           period_year=2026, amount_due=Decimal('30'), due_date=today + timedelta(5))

        data = ReportService.get_management_dashboard(self.tenant1, date(2026, 1, 1), date(2026, 12, 31), today=today)

        self.assertEqual(data['income_statement']['net_profit'], Decimal('500'))
        self.assertEqual(data['expenses']['by_currency']['USD']['total'], Decimal('1200'))
        self.assertEqual(data['expenses']['pending_approval'], 1)
        self.assertEqual(data['budgets'][0]['percent_used'], Decimal('120.00'))
        self.assertEqual(data['obligations']['overdue_count'], 1)
        self.assertEqual(data['obligations']['open_amount'], Decimal('100'))
        self.assertEqual(len(data['obligations']['upcoming']), 1)
        levels = [a['level'] for a in data['alerts']]
        self.assertIn('danger', levels)
        self.assertTrue(any('excedido' in a['message'] for a in data['alerts']))

    def test_dashboard_endpoint(self):
        response = self.client_for(self.viewer).get(f'{REPORTS}/dashboard/?tenant_id={self.tenant1.id}')
        self.assertEqual(response.status_code, 200)
        for key in ('income_statement', 'cash', 'receivables', 'expenses', 'budgets', 'investments',
                    'obligations', 'alerts'):
            self.assertIn(key, response.data)


class PayrollConfigTests(TestCase):

    def setUp(self):
        from django.contrib.auth import get_user_model
        self.tenant = Tenant.objects.create(name='Otra', slug='otra')
        self.user = get_user_model().objects.create_user('emp', password='x')

    def test_uganda_preset_keeps_original_rules(self):
        TenantSetting.objects.create(tenant=self.tenant, setting_key='payroll_config', setting_value={'country': 'UG'})
        config = get_payroll_config(self.tenant)
        self.assertEqual(config['income_tax']['code'], 'paye')
        self.assertEqual(PayrollService.calculate_paye(Decimal('300000')), Decimal('6500.00'))
        self.assertEqual(PayrollService.calculate_paye(Decimal('20000000')),
                         Decimal('10000') + Decimal('15000') + Decimal('2877000') + Decimal('4000000'))

    def test_generic_progressive_bands(self):
        bands = [[1000, 0], [2000, 10], [None, 25]]
        self.assertEqual(PayrollService.calculate_income_tax(Decimal('500'), bands), Decimal('0.00'))
        self.assertEqual(PayrollService.calculate_income_tax(Decimal('1500'), bands), Decimal('50.00'))
        self.assertEqual(PayrollService.calculate_income_tax(Decimal('3000'), bands), Decimal('350.00'))

    def test_social_security_cap(self):
        employee, employer = PayrollService.calculate_nssf(
            Decimal('5000'), {'employee_rate': 4, 'employer_rate': 9, 'monthly_cap': 2000})
        self.assertEqual((employee, employer), (Decimal('80.00'), Decimal('180.00')))

    def test_invalid_configs_are_rejected(self):
        for bad in ({'income_tax': {'bands': []}},
                    {'income_tax': {'bands': [[100, 5], [50, 10]]}},
                    {'income_tax': {'bands': [[None, 5], [100, 10]]}},
                    {'income_tax': {'bands': [[100, 150]]}},
                    {'social_security': {'employee_rate': -1}},
                    {'due_day': 40},
                    'no es un objeto'):
            with self.subTest(config=bad), self.assertRaises(PayrollConfigError):
                validate_payroll_config(bad)

    def test_monthly_run_uses_tenant_config(self):
        TenantSetting.objects.create(tenant=self.tenant, setting_key='payroll_config', setting_value={
            'income_tax': {'code': 'income_tax', 'bands': [[1000, 0], [None, 10]]},
            'social_security': {'code': 'social_security', 'employee_rate': 4, 'employer_rate': 8},
            'due_day': 20,
        })
        EmployeePayrollProfile.objects.create(tenant=self.tenant, user=self.user, employee_number='1',
                                              gross_salary=Decimal('3000'), start_date=date(2026, 1, 1))
        run = PayrollService.run_monthly_payroll(self.tenant, 12, 2026, self.user)
        self.assertEqual(run.total_paye, Decimal('200.00'))
        self.assertEqual(run.total_nssf_employee, Decimal('120.00'))
        self.assertEqual(run.total_net, Decimal('2680.00'))
        tax = StatutoryObligation.objects.get(tenant=self.tenant, obligation_type='income_tax')
        social = StatutoryObligation.objects.get(tenant=self.tenant, obligation_type='social_security')
        self.assertEqual(tax.due_date, date(2027, 1, 20))
        self.assertEqual(social.amount_due, Decimal('360.00'))


class TenantSettingValidationTests(ManagementTestBase):
    url = '/api/tenants/settings/'

    def test_api_rejects_invalid_payroll_config(self):
        response = self.client_for(self.admin).post(self.url, {
            'tenant': self.tenant1.id, 'setting_key': 'payroll_config',
            'setting_value': {'income_tax': {'bands': [[100, 5], [50, 10]]}}}, format='json')
        self.assertEqual(response.status_code, 400)

    def test_api_accepts_valid_payroll_config(self):
        response = self.client_for(self.admin).post(self.url, {
            'tenant': self.tenant1.id, 'setting_key': 'payroll_config',
            'setting_value': {'social_security': {'employee_rate': 3}}}, format='json')
        self.assertEqual(response.status_code, 201)
