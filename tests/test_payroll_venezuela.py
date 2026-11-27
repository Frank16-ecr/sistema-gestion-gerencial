"""Nomina con el preset de Venezuela (ISLR por AR-I, IVSS, RPE, FAOV, INCES, pensiones).

Caso de referencia (noviembre 2026, 5 lunes), calculado a mano con salario minimo Bs 130:
salario 1.000 + bono 500 = 1.500 (base "total").
- IVSS  (semanal) base mensual min(1000, 5x130=650) = 650 -> semanal 650x12/52 = 150 -> x5 lunes = 750
        trabajador 4% 30,00 | patrono 9% 67,50
- RPE   (semanal) base mensual min(1000, 1300) = 1000 -> 1000x12/52x5 = 1.153,85
        trabajador 0,5% 5,77 | patrono 2% 23,08
- FAOV  base 1.500 -> trabajador 1% 15,00 | patrono 2% 30,00
- INCES base 1.500 ->                       patrono 2% 30,00
- Pensiones base 1.500 ->                   patrono 9% 135,00
- ISLR 2% (AR-I) sobre 1.500 = 30,00
Neto = 1.500 - 30 - (30 + 5,77 + 15) = 1.419,23
"""
from datetime import date
from decimal import Decimal
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings

from finance.payroll.config import PayrollConfigError, get_payroll_config, validate_payroll_config
from finance.payroll.models import EmployeeAllowance, EmployeePayrollProfile
from finance.payroll.services import PayrollService
from finance.statutory.models import StatutoryObligation
from tenants.config import base_currency
from tenants.models import Tenant, TenantSetting

User = get_user_model()


@override_settings(PAYROLL_COUNTRY='VE')
class VenezuelaPayrollTests(TestCase):

    def setUp(self):
        self.tenant = Tenant.objects.create(name='Empresa VE', slug='ve')
        self.user = User.objects.create_user('rrhh', password='x')

    def add_employee(self, number='1', salary='1000', rate='2', bonus='500'):
        emp = EmployeePayrollProfile.objects.create(
            tenant=self.tenant, user=User.objects.create_user(f'emp{number}', password='x'),
            employee_number=number, gross_salary=Decimal(salary), start_date=date(2026, 1, 1),
            income_tax_rate=Decimal(rate) if rate is not None else None,
        )
        if bonus:
            EmployeeAllowance.objects.create(employee=emp, allowance_type='other', amount=Decimal(bonus))
        return emp

    def obligations(self):
        return dict(StatutoryObligation.objects.filter(tenant=self.tenant)
                    .values_list('obligation_type', 'amount_due'))

    def test_default_country_is_venezuela(self):
        config = get_payroll_config(self.tenant)
        self.assertEqual(config['income_tax']['method'], 'employee_rate')
        self.assertEqual([c['code'] for c in config['contributions']], ['ivss', 'rpe', 'faov', 'inces', 'pension'])

    def test_reference_payroll(self):
        self.add_employee()
        run = PayrollService.run_monthly_payroll(self.tenant, 11, 2026, self.user)
        line = run.lines.get()
        self.assertEqual(run.mondays, 5)
        self.assertEqual(line.paye, Decimal('30.00'))
        self.assertEqual(line.nssf_employee, Decimal('50.77'))
        self.assertEqual(line.nssf_employer, Decimal('285.58'))
        self.assertEqual(line.net_pay, Decimal('1419.23'))
        self.assertEqual(line.contributions['ivss'], {'base': '750.00', 'employee': '30.00', 'employer': '67.50'})
        self.assertEqual(run.contributions_summary['pension']['employer'], '135.00')
        self.assertEqual(self.obligations(), {
            'islr': Decimal('30.00'), 'ivss': Decimal('97.50'), 'rpe': Decimal('28.85'),
            'faov': Decimal('45.00'), 'inces': Decimal('30.00'), 'pension': Decimal('135.00'),
        })
        due = StatutoryObligation.objects.get(tenant=self.tenant, obligation_type='ivss').due_date
        self.assertEqual(due, date(2026, 12, 15))

    def test_employee_without_ari_rate_has_no_withholding(self):
        self.add_employee(rate=None)
        run = PayrollService.run_monthly_payroll(self.tenant, 11, 2026, self.user)
        self.assertEqual(run.total_paye, Decimal('0.00'))
        self.assertNotIn('islr', self.obligations())

    def test_minimum_wage_change_moves_caps(self):
        TenantSetting.objects.create(tenant=self.tenant, setting_key='payroll_config',
                                     setting_value={'minimum_wage': 1000})
        self.add_employee(bonus=None)
        run = PayrollService.run_monthly_payroll(self.tenant, 11, 2026, self.user)
        # Con salario minimo 1.000 el tope del IVSS (5.000) ya no recorta: 1000x12/52x5 lunes x 4%.
        self.assertEqual(run.lines.get().contributions['ivss']['employee'], '46.15')

    def test_pension_floor_and_contribution_due_day(self):
        config = validate_payroll_config({'country': 'VE'})
        for c in config['contributions']:
            if c['code'] == 'pension':
                c['floor_amount'] = 2000
                c['due_day'] = 5
        TenantSetting.objects.create(tenant=self.tenant, setting_key='payroll_config',
                                     setting_value={'contributions': config['contributions']})
        self.add_employee(bonus=None)
        PayrollService.run_monthly_payroll(self.tenant, 12, 2026, self.user)
        pension = StatutoryObligation.objects.get(tenant=self.tenant, obligation_type='pension')
        self.assertEqual(pension.amount_due, Decimal('180.00'))
        self.assertEqual(pension.due_date, date(2027, 1, 5))

    def test_invalid_venezuelan_configs(self):
        for bad in ({'country': 'XX'},
                    {'minimum_wage': 0},
                    {'minimum_wage': None},
                    {'income_tax': {'method': 'magia'}},
                    {'contributions': [{'code': 'a'}, {'code': 'a'}]},
                    {'contributions': [{'code': 'a', 'base': 'otra'}]},
                    {'contributions': [{'code': 'a', 'employer_rate': 120}]},
                    {'contributions': [{'code': 'a', 'cap_amount': -5}]},
                    {'contributions': [{'code': 'a', 'due_day': 0}]},
                    {'contributions': [{'nombre': 'sin codigo'}]}):
            with self.subTest(config=bad), self.assertRaises(PayrollConfigError):
                validate_payroll_config(bad)


class ConfigurarPaisCommandTests(TestCase):

    def setUp(self):
        self.tenant = Tenant.objects.create(name='Andina', slug='andina')

    def setting(self, key):
        return TenantSetting.objects.get(tenant=self.tenant, setting_key=key).setting_value

    def test_configures_venezuela(self):
        out = StringIO()
        call_command('configurar_pais', 'andina', 'VE', '--riesgo', 'alto', '--salario-minimo', '130',
                     '--piso-pensiones', '5000', stdout=out)
        self.assertEqual(base_currency(self.tenant), 'VES')
        config = get_payroll_config(self.tenant)
        rates = {c['code']: c for c in config['contributions']}
        self.assertEqual(rates['ivss']['employer_rate'], 11)
        self.assertEqual(rates['pension']['floor_amount'], 5000)
        self.assertEqual(config['minimum_wage'], 130)
        self.assertIn('configuradas', out.getvalue())

    def test_custom_currency_and_rerun_updates(self):
        call_command('configurar_pais', 'andina', 'VE', stdout=StringIO())
        call_command('configurar_pais', 'andina', 'VE', '--moneda', 'USD', stdout=StringIO())
        self.assertEqual(self.setting('base_currency'), 'USD')
        self.assertEqual(TenantSetting.objects.filter(tenant=self.tenant).count(), 2)

    def test_errors(self):
        with self.assertRaises(CommandError):
            call_command('configurar_pais', 'no-existe', 'VE', stdout=StringIO())
        with self.assertRaises(CommandError):
            call_command('configurar_pais', 'andina', 'UG', '--riesgo', 'bajo', stdout=StringIO())


class CargarDemoTests(TestCase):

    def test_creates_demo_and_reset_recreates_it(self):
        from finance.accounts.models import JournalEntry
        from finance.reports.services import ReportService
        from finance.sales.models import Invoice

        User.objects.create_user('frank', password='x')
        call_command('cargar_demo', '--usuario', 'frank', stdout=StringIO())
        with self.assertRaises(CommandError):
            call_command('cargar_demo', stdout=StringIO())
        call_command('cargar_demo', '--reset', stdout=StringIO())
        tenant = Tenant.objects.get(slug='demo')
        self.assertEqual(Tenant.objects.filter(slug='demo').count(), 1)
        self.assertTrue(Invoice.objects.filter(tenant=tenant, status='paid').exists())
        self.assertTrue(JournalEntry.objects.filter(tenant=tenant).exists())
        today = date.today()
        self.assertTrue(ReportService.get_balance_sheet(tenant, today)['is_balanced'])
        data = ReportService.get_management_dashboard(tenant, date(today.year, 1, 1), today)
        self.assertIn('USD', data['receivables'])
        self.assertTrue(data['alerts'])
