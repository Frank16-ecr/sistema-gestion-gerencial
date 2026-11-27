"""Crea una empresa de DEMOSTRACION con datos de ejemplo para ver el sistema funcionando.

    python manage.py cargar_demo
    python manage.py cargar_demo --reset            # borra la demo y la vuelve a crear
    python manage.py cargar_demo --usuario frank    # ademas da rol de administrador a ese usuario

Todos los datos son ficticios, incluidas las tasas de cambio (no son tasas reales del BCV).
"""
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from finance.accounts.models import JournalEntry, JournalLine
from finance.accounts.services import create_chart_of_accounts
from finance.banking.models import BankAccount
from finance.budgets.models import Budget, BudgetLine
from finance.expenses.models import Expense
from finance.fx.models import ExchangeRate
from finance.investments.models import Investment, InvestmentMovement
from finance.payroll.models import EmployeeAllowance, EmployeePayrollProfile
from finance.payroll.services import PayrollService
from finance.sales import services as sales
from finance.sales.models import Customer, Invoice, InvoiceLine, InvoicePayment, TaxpayerProfile, VatWithholding
from finance.security.models import UserTenantRole
from finance.statutory.models import StatutoryObligation
from tenants.models import Tenant, TenantSetting

DEMO_SLUG = 'demo'
D = Decimal
User = get_user_model()


def demo_rate(day_index):
    """Tasa ficticia que sube suavemente (Bs por USD)."""
    return (D('300') + D('0.35') * day_index).quantize(D('0.0001'))


class Command(BaseCommand):
    help = 'Crea una empresa de demostracion con datos ficticios.'

    def add_arguments(self, parser):
        parser.add_argument('--reset', action='store_true', help='borra la demo existente y la recrea')
        parser.add_argument('--usuario', help='usuario al que dar rol de administrador en la demo')

    def handle(self, *args, **opts):
        existing = Tenant.objects.filter(slug=DEMO_SLUG).first()
        if existing and not opts['reset']:
            raise CommandError('La empresa demo ya existe. Usa --reset para borrarla y crearla de nuevo.')
        with transaction.atomic():
            if existing:
                self._delete(existing)
            tenant = self._create(opts.get('usuario'))
        self.stdout.write(self.style.SUCCESS(
            f'Empresa "{tenant.name}" creada con datos de ejemplo. Abre /panel/ y elige esa empresa.'))
        self.stdout.write('Recuerda: todos los datos y tasas son ficticios.')

    # ------------------------------------------------------------------

    def _delete(self, tenant):
        """Borra la demo respetando las relaciones protegidas."""
        JournalLine.objects.filter(tenant=tenant).delete()
        JournalEntry.objects.filter(tenant=tenant).delete()
        InvoicePayment.objects.filter(tenant=tenant).delete()
        VatWithholding.objects.filter(tenant=tenant).delete()
        Invoice.objects.filter(tenant=tenant, related_invoice__isnull=False).delete()
        Invoice.objects.filter(tenant=tenant).delete()
        tenant.delete()
        User.objects.filter(username__startswith='demo_empleado_').delete()

    def _create(self, username):
        today = date.today()
        tenant = Tenant.objects.create(name='Comercial Andina (DEMO)', slug=DEMO_SLUG)
        TenantSetting.objects.create(tenant=tenant, setting_key='base_currency', setting_value='VES')
        TenantSetting.objects.create(tenant=tenant, setting_key='payroll_config',
                                     setting_value={'country': 'VE', 'minimum_wage': 130})
        create_chart_of_accounts(tenant)
        if username:
            user = User.objects.filter(username=username).first()
            if user is None:
                raise CommandError(f'No existe el usuario "{username}".')
            UserTenantRole.objects.create(tenant=tenant, user=user, role='admin')

        # Tasas de cambio ficticias de los ultimos 100 dias
        start = today - timedelta(days=100)
        for i in range(101):
            day = start + timedelta(days=i)
            ExchangeRate.objects.create(tenant=tenant, from_currency='USD', to_currency='VES',
                                        rate=demo_rate(i), rate_date=day, source='manual')
            ExchangeRate.objects.create(tenant=tenant, from_currency='EUR', to_currency='VES',
                                        rate=(demo_rate(i) * D('1.08')).quantize(D('0.0001')),
                                        rate_date=day, source='manual')

        self._sales(tenant, today)
        self._expenses_and_budget(tenant, today)
        self._banks_and_investments(tenant, today)
        self._payroll(tenant, today)
        self._overdue_obligation(tenant, today)
        return tenant

    def _sales(self, tenant, today):
        TaxpayerProfile.objects.create(
            tenant=tenant, rif='J-40123456-7', legal_name='Comercial Andina (DEMO), C.A.',
            fiscal_address='Av. Principal, Caracas', is_special_taxpayer=True, igtf_collection_agent=True,
        )
        clientes = [
            Customer.objects.create(tenant=tenant, rif='J-30111222-3', name='Distribuidora Ejemplo, C.A.',
                                    is_special_taxpayer=True, vat_withholding_percent=75),
            Customer.objects.create(tenant=tenant, rif='J-29444555-1', name='Servicios Modelo, S.A.'),
            Customer.objects.create(tenant=tenant, rif='V-12345678-9', name='Maria Perez (cliente demo)'),
        ]

        def factura(cliente, dias_atras, moneda, lineas, vence=30):
            emision = today - timedelta(days=dias_atras)
            inv = Invoice.objects.create(tenant=tenant, customer=cliente, currency=moneda, issue_date=emision,
                                         due_date=emision + timedelta(days=vence))
            for descripcion, cantidad, precio, categoria in lineas:
                InvoiceLine.objects.create(invoice=inv, description=descripcion, quantity=D(cantidad),
                                           unit_price=D(precio), tax_category=categoria)
            sales.recalculate(inv)
            return sales.issue_invoice(inv)

        f1 = factura(clientes[0], 55, 'USD', [('Consultoria mensual', '1', '1200', 'general'),
                                              ('Licencia de software', '2', '150', 'general')])
        sales.register_vat_withholding(f1, f'{(today - timedelta(days=50)):%Y%m}00000001',
                                       today - timedelta(days=50))
        f1.refresh_from_db()
        sales.register_payment(f1, today - timedelta(days=45), f1.balance_due, 'USD', 'zelle', 'ZL-1001')

        f2 = factura(clientes[1], 40, 'VES', [('Mantenimiento de equipos', '3', '18000', 'general'),
                                              ('Repuestos', '5', '2500', 'reduced'),
                                              ('Traslado', '1', '4000', 'exempt')])
        sales.register_payment(f2, today - timedelta(days=20), D('40000'), 'VES', 'transfer', 'TRF-55821')

        f3 = factura(clientes[2], 25, 'USD', [('Asesoria contable', '1', '300', 'general')], vence=15)
        sales.register_payment(f3, today - timedelta(days=5), D('348'), 'USD', 'cash_foreign', 'EFECTIVO')

        f4 = factura(clientes[0], 12, 'USD', [('Consultoria mensual', '1', '1200', 'general'),
                                              ('Equipo importado (suntuario)', '1', '800', 'luxury')])
        nota = Invoice.objects.create(tenant=tenant, customer=clientes[0], currency='USD', doc_type='credit_note',
                                      related_invoice=f4, issue_date=today - timedelta(days=8))
        InvoiceLine.objects.create(invoice=nota, description='Descuento por pronto pago', quantity=1,
                                   unit_price=D('100'), tax_category='general')
        sales.recalculate(nota)
        sales.issue_invoice(nota)

        # Factura vencida sin cobrar, para ver alertas de cobranza
        factura(clientes[1], 70, 'USD', [('Soporte tecnico', '10', '45', 'general')], vence=20)

        borrador = Invoice.objects.create(tenant=tenant, customer=clientes[1], currency='VES', issue_date=today)
        InvoiceLine.objects.create(invoice=borrador, description='Servicio pendiente de facturar', quantity=1,
                                   unit_price=D('25000'), tax_category='general')
        sales.recalculate(borrador)

    def _expenses_and_budget(self, tenant, today):
        year_start = date(today.year, 1, 1)
        budget = Budget.objects.create(
            tenant=tenant, name=f'Presupuesto operativo {today.year}', fiscal_year=today.year, currency='VES',
            period_start=year_start, period_end=date(today.year, 12, 31), status='approved',
        )
        plan = {'rent': '720000', 'utilities': '150000', 'travel': '90000', 'office_supplies': '60000',
                'internet': '48000'}
        for category, amount in plan.items():
            BudgetLine.objects.create(budget=budget, category=category, planned_amount=D(amount))

        gastos = [
            ('Alquiler de oficina', 'rent', '60000', 10, 'paid'),
            ('Alquiler de oficina', 'rent', '60000', 40, 'paid'),
            ('Electricidad y agua', 'utilities', '14500', 15, 'approved'),
            ('Viaje a Valencia (clientes)', 'travel', '52000', 20, 'approved'),
            ('Viaje a Maracaibo (clientes)', 'travel', '47000', 35, 'approved'),
            ('Papeleria y toner', 'office_supplies', '8200', 7, 'approved'),
            ('Internet fibra', 'internet', '4000', 3, 'approved'),
            ('Combustible flota', 'fuel', '12600', 2, 'pending'),
            ('Reparacion aire acondicionado', 'other', '18000', 1, 'pending'),
        ]
        for descripcion, categoria, monto, dias_atras, estado in gastos:
            Expense.objects.create(tenant=tenant, description=descripcion, category=categoria, amount=D(monto),
                                   currency='VES', expense_date=today - timedelta(days=dias_atras), status=estado)

    def _banks_and_investments(self, tenant, today):
        BankAccount.objects.create(tenant=tenant, account_name='Cuenta corriente', bank_name='Banco Ejemplo',
                                   account_number='0102-0000-00-0000000001', currency='VES',
                                   current_balance=D('845320.55'))
        BankAccount.objects.create(tenant=tenant, account_name='Cuenta en divisas', bank_name='Banco Ejemplo',
                                   account_number='0102-0000-00-0000000002', currency='USD',
                                   current_balance=D('12450.00'))
        BankAccount.objects.create(tenant=tenant, account_name='Caja chica', bank_name='-', account_number='CAJA',
                                   currency='VES', account_type='petty_cash', current_balance=D('15000'))
        inversion = Investment.objects.create(
            tenant=tenant, name='Deposito a plazo 180 dias', asset_type='term_deposit', institution='Banco Ejemplo',
            currency='USD', initial_amount=D('10000'), start_date=today - timedelta(days=90),
            maturity_date=today + timedelta(days=90), expected_return_rate=D('6'),
        )
        InvestmentMovement.objects.create(investment=inversion, movement_type='return', amount=D('150'),
                                          movement_date=today - timedelta(days=30))

    def _payroll(self, tenant, today):
        empleados = [
            ('Ana', 'Rodriguez', '4500', '3'),
            ('Luis', 'Gonzalez', '3200', '1.5'),
            ('Carla', 'Mendoza', '2600', None),
            ('Jose', 'Ramirez', '6800', '6'),
        ]
        for i, (nombre, apellido, salario, islr) in enumerate(empleados, start=1):
            user = User.objects.create_user(f'demo_empleado_{i}', first_name=nombre, last_name=apellido)
            user.set_unusable_password()
            user.save()
            emp = EmployeePayrollProfile.objects.create(
                tenant=tenant, user=user, employee_number=f'E-{i:03d}', gross_salary=D(salario),
                start_date=today - timedelta(days=400), income_tax_rate=D(islr) if islr else None,
            )
            EmployeeAllowance.objects.create(employee=emp, allowance_type='transport', amount=D('800'),
                                             is_taxable=False)
            EmployeeAllowance.objects.create(employee=emp, allowance_type='lunch', amount=D('1200'))

        prev_month_last = today.replace(day=1) - timedelta(days=1)
        for period in ('q1', 'q2'):
            run = PayrollService.run_payroll(tenant, prev_month_last.month, prev_month_last.year, None, period)
            PayrollService.approve(run, None)
        if today.day > 15:
            PayrollService.run_payroll(tenant, today.month, today.year, None, 'q1')

    def _overdue_obligation(self, tenant, today):
        # Lo ya vencido se da por pagado, como en una empresa al dia...
        StatutoryObligation.objects.filter(tenant=tenant, due_date__lt=today).update(status='paid')
        # ...salvo una obligacion vencida, para ver la alerta.
        StatutoryObligation.objects.update_or_create(
            tenant=tenant, obligation_type='inces', period_month=1, period_year=today.year,
            defaults={'amount_due': D('8400'), 'due_date': today - timedelta(days=10), 'status': 'pending'},
        )
