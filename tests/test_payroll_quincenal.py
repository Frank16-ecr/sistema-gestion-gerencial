"""Nomina quincenal (Venezuela), cotizacion semanal por lunes y asiento de nomina."""
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from rest_framework.test import APIClient

from finance.accounts.services import create_chart_of_accounts
from finance.payroll.models import EmployeeAllowance, EmployeePayrollProfile
from finance.payroll.services import PayrollError, PayrollService, count_mondays
from finance.security.models import UserTenantRole
from finance.statutory.models import StatutoryObligation
from tenants.models import Tenant

User = get_user_model()
D = Decimal


@override_settings(PAYROLL_COUNTRY='VE')
class QuincenaTests(TestCase):

    def setUp(self):
        self.tenant = Tenant.objects.create(name='VE', slug='ve')
        self.user = User.objects.create_user('rrhh', password='x')
        emp = EmployeePayrollProfile.objects.create(
            tenant=self.tenant, user=User.objects.create_user('e1', password='x'), employee_number='1',
            gross_salary=D('1000'), start_date=date(2026, 1, 1), income_tax_rate=D('2'),
        )
        EmployeeAllowance.objects.create(employee=emp, allowance_type='other', amount=D('500'))

    def test_count_mondays(self):
        self.assertEqual(count_mondays(date(2026, 11, 1), date(2026, 11, 15)), 2)
        self.assertEqual(count_mondays(date(2026, 11, 16), date(2026, 11, 30)), 3)
        self.assertEqual(count_mondays(date(2026, 11, 3), date(2026, 11, 8)), 0)

    def test_quincenas_split_and_obligations_add_up(self):
        q1 = PayrollService.run_payroll(self.tenant, 11, 2026, self.user, 'q1')
        q2 = PayrollService.run_payroll(self.tenant, 11, 2026, self.user, 'q2')
        line1, line2 = q1.lines.get(), q2.lines.get()
        self.assertEqual((q1.period_start, q1.period_end, q1.mondays), (date(2026, 11, 1), date(2026, 11, 15), 2))
        self.assertEqual((line1.gross_salary, line1.total_allowances), (D('500.00'), D('250.00')))
        self.assertEqual(line1.paye, D('15.00'))                          # 2% de 750
        # IVSS semanal: 650 x 12/52 = 150 por semana -> 2 lunes = 300 -> 4% = 12,00 ; 3 lunes -> 18,00
        self.assertEqual(line1.contributions['ivss']['employee'], '12.00')
        self.assertEqual(line2.contributions['ivss']['employee'], '18.00')
        self.assertEqual(line1.contributions['faov']['employee'], '7.50')  # la mitad del 1% de 1.500
        ivss = StatutoryObligation.objects.get(tenant=self.tenant, obligation_type='ivss')
        self.assertEqual(ivss.amount_due, D('97.50'))   # igual que la nomina mensual de 5 lunes
        islr = StatutoryObligation.objects.get(tenant=self.tenant, obligation_type='islr')
        self.assertEqual(islr.amount_due, D('30.00'))

    def test_monthly_and_quincenas_are_exclusive(self):
        PayrollService.run_payroll(self.tenant, 11, 2026, self.user, 'q1')
        with self.assertRaises(PayrollError):
            PayrollService.run_payroll(self.tenant, 11, 2026, self.user, 'monthly')
        PayrollService.run_payroll(self.tenant, 12, 2026, self.user, 'monthly')
        with self.assertRaises(PayrollError):
            PayrollService.run_payroll(self.tenant, 12, 2026, self.user, 'q2')
        with self.assertRaises(PayrollError):
            PayrollService.run_payroll(self.tenant, 12, 2026, self.user, 'semanal')

    def test_employee_hired_later_is_not_paid(self):
        EmployeePayrollProfile.objects.create(
            tenant=self.tenant, user=User.objects.create_user('nuevo', password='x'), employee_number='2',
            gross_salary=D('1000'), start_date=date(2026, 11, 20))
        self.assertEqual(PayrollService.run_payroll(self.tenant, 11, 2026, self.user, 'q1').lines.count(), 1)
        self.assertEqual(PayrollService.run_payroll(self.tenant, 11, 2026, self.user, 'q2').lines.count(), 2)

    def test_approve_posts_balanced_entry(self):
        create_chart_of_accounts(self.tenant)
        run = PayrollService.run_payroll(self.tenant, 11, 2026, self.user, 'q1')
        run = PayrollService.approve(run, self.user)
        self.assertEqual(run.status, 'approved')
        lines = list(run.journal_entry.lines.all())
        self.assertEqual(sum(x.debit_amount for x in lines), sum(x.credit_amount for x in lines))
        salaries = next(x for x in lines if x.account.code == '5.1.01')
        self.assertEqual(salaries.debit_amount, D('750.00'))
        with self.assertRaises(PayrollError):
            PayrollService.approve(run, self.user)

    def test_api_period_and_read_only_status(self):
        manager = User.objects.create_user('gerente', password='x')
        UserTenantRole.objects.create(tenant=self.tenant, user=manager, role='manager')
        api = APIClient()
        api.force_authenticate(manager)
        response = api.post('/api/finance/payroll/runs/run_monthly/',
                            {'tenant_id': self.tenant.id, 'month': 11, 'year': 2026, 'period': 'q2'})
        self.assertEqual((response.status_code, response.data['period'], response.data['mondays']), (200, 'q2', 3))
        pk = response.data['id']
        api.patch(f'/api/finance/payroll/runs/{pk}/', {'status': 'paid'}, format='json')
        self.assertEqual(api.get(f'/api/finance/payroll/runs/{pk}/').data['status'], 'draft')
        bad = api.post('/api/finance/payroll/runs/run_monthly/',
                       {'tenant_id': self.tenant.id, 'month': 11, 'year': 2026, 'period': 'monthly'})
        self.assertEqual(bad.status_code, 400)
        no_chart = api.post(f'/api/finance/payroll/runs/{pk}/approve/')
        self.assertEqual(no_chart.status_code, 400)
        self.assertIn('crear_plan_cuentas', no_chart.data['error'])
