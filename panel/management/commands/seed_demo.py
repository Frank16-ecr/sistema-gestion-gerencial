"""Carga una empresa de ejemplo para ver el panel con datos: python manage.py seed_demo"""

import random
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from finance.accounts.models import Account, JournalEntry, JournalLine
from finance.banking.models import BankAccount, BankReconciliation, Cheque, PettyCashTransaction
from finance.budgets.models import Budget, BudgetLine
from finance.expenses.models import Expense
from finance.investments.models import Investment, InvestmentMovement
from finance.invoicing.models import FeeNote
from finance.payments.services import PaymentService
from finance.payroll.models import EmployeeAllowance, EmployeePayrollProfile
from finance.payroll.services import PayrollService
from finance.security.models import UserTenantRole
from tenants.models import Tenant

SLUG = 'empresa-demo'

PLAN = {  # categoria: (planificado anual, gasto mensual aproximado)
    'rent': (24000, 2000),
    'utilities': (6000, 480),
    'internet': (1800, 150),
    'travel': (9000, 900),
    'office_supplies': (3000, 230),
    'fuel': (2400, 220),
}
DESCRIPTIONS = {
    'rent': 'Alquiler de oficina',
    'utilities': 'Electricidad y agua',
    'internet': 'Plan de internet',
    'travel': 'Viaje de visita a clientes',
    'office_supplies': 'Papelería y suministros',
    'fuel': 'Combustible',
    'other': 'Gasto varios',
}


class Command(BaseCommand):
    help = 'Crea una empresa de ejemplo con presupuesto, gastos e inversiones. Usa --reset para recrearla.'

    def add_arguments(self, parser):
        parser.add_argument('--reset', action='store_true', help='Borra la empresa de ejemplo y la crea de nuevo.')

    def handle(self, *args, **options):
        existing = Tenant.objects.filter(slug=SLUG)
        if existing.exists():
            if not options['reset']:
                self.stdout.write(self.style.WARNING('La empresa de ejemplo ya existe. Usa --reset para recrearla.'))
                return
            # Las lineas de asiento protegen a las cuentas: se borran primero.
            JournalLine.objects.filter(tenant__slug=SLUG).delete()
            existing.delete()

        rng = random.Random(42)  # datos repetibles
        today = timezone.localdate()
        year = today.year
        tenant = Tenant.objects.create(name='Empresa Demo', slug=SLUG)

        budget = Budget.objects.create(
            tenant=tenant,
            name='Presupuesto operativo',
            fiscal_year=year,
            status='approved',
            period_start=date(year, 1, 1),
            period_end=date(year, 12, 31),
            currency='USD',
            approved_at=timezone.now(),
            notes='Presupuesto de ejemplo generado por seed_demo.',
        )
        for category, (planned, _monthly) in PLAN.items():
            BudgetLine.objects.create(budget=budget, category=category, planned_amount=Decimal(planned))
        Budget.objects.create(
            tenant=tenant,
            name='Plan de capacitación',
            fiscal_year=year,
            status='draft',
            period_start=date(year, 1, 1),
            period_end=date(year, 12, 31),
            currency='USD',
        )

        expenses = 0
        for month in range(1, today.month + 1):
            for category, (_planned, monthly) in PLAN.items():
                amount = Decimal(monthly) * Decimal(rng.uniform(0.8, 1.25)).quantize(Decimal('0.01'))
                last_month = month == today.month
                status = 'pending' if last_month and category in ('travel', 'fuel') else 'paid'
                max_day = today.day if last_month else 28  # nunca fechas futuras
                Expense.objects.create(
                    tenant=tenant,
                    description=DESCRIPTIONS[category],
                    category=category,
                    amount=amount.quantize(Decimal('0.01')),
                    currency='USD',
                    expense_date=date(year, month, rng.randint(1, max_day)),
                    status=status,
                )
                expenses += 1
        # Un gasto fuera del presupuesto y uno rechazado, para ver esos casos.
        Expense.objects.create(
            tenant=tenant,
            description='Multa administrativa',
            category='other',
            amount=Decimal('320.00'),
            currency='USD',
            expense_date=date(year, 3, 12),
            status='paid',
        )
        Expense.objects.create(
            tenant=tenant,
            description='Cena de equipo',
            category='other',
            amount=Decimal('180.00'),
            currency='USD',
            expense_date=date(year, 4, 2),
            status='rejected',
        )

        deposito = Investment.objects.create(
            tenant=tenant,
            name='Depósito a plazo',
            asset_type='term_deposit',
            institution='Banco Central',
            initial_amount=Decimal('50000'),
            start_date=date(year, 1, 15),
            maturity_date=date(year + 1, 1, 15),
            expected_return_rate=Decimal('6.5'),
            currency='USD',
        )
        fondo = Investment.objects.create(
            tenant=tenant,
            name='Fondo de renta fija',
            asset_type='fund',
            institution='Fondo Andino',
            initial_amount=Decimal('20000'),
            start_date=date(year, 2, 1),
            expected_return_rate=Decimal('4.2'),
            currency='EUR',
        )
        bonos = Investment.objects.create(
            tenant=tenant,
            name='Bonos corporativos',
            asset_type='bond',
            institution='Mesa de dinero',
            initial_amount=Decimal('15000'),
            start_date=date(year, 3, 1),
            maturity_date=date(year + 2, 3, 1),
            expected_return_rate=Decimal('7.8'),
            currency='USD',
        )
        moves = [
            (deposito, 'contribution', '10000', 3),
            (deposito, 'return', '1250', 6),
            (deposito, 'withdrawal', '2000', 8),
            (deposito, 'fee', '45', 8),
            (fondo, 'return', '310', 5),
            (fondo, 'return', '295', 8),
            (fondo, 'fee', '25', 8),
            (bonos, 'return', '585', 6),
            (bonos, 'return', '585', 9),
        ]
        for investment, kind, amount, month in moves:
            if month <= today.month:
                InvestmentMovement.objects.create(
                    investment=investment,
                    movement_type=kind,
                    amount=Decimal(amount),
                    movement_date=date(year, month, 1),
                )

        self.seed_operations(tenant, today)

        self.stdout.write(
            self.style.SUCCESS(
                f'Listo: "Empresa Demo" con 2 presupuestos, {expenses + 2} gastos, 3 inversiones, '
                'notas de honorarios, nómina, bancos y contabilidad.'
            )
        )
        self.stdout.write(
            'Si eres superusuario, ya la ves en el panel. ' 'Un usuario normal necesita un rol en esa empresa.'
        )

    # ------------------------------------------------------------------ cobros, nomina, tesoreria, contabilidad

    def seed_operations(self, tenant, today):
        User = get_user_model()
        admin = User.objects.filter(is_superuser=True).first()
        self.seed_billing(tenant, today, admin)
        self.seed_payroll(tenant, today, admin)
        self.seed_treasury(tenant, today)
        self.seed_accounting(tenant, today, admin)

    def seed_billing(self, tenant, today, admin):
        import uuid

        def note(number, insurer, amount, vat, days_ago, due_days, status):
            total = Decimal(amount) + Decimal(vat)
            return FeeNote.objects.create(
                tenant=tenant,
                fee_note_number=number,
                claim_id=uuid.uuid4(),
                insurer_id=uuid.uuid4(),
                insurer_name=insurer,
                insurer_email=f'cobros@{insurer.split()[0].lower()}.example',
                invoice_currency='USD',
                invoice_amount=Decimal(amount),
                vat_amount=Decimal(vat),
                total_amount=total,
                exchange_rate_at_issue=Decimal('3700'),
                base_currency_amount=total * 3700,
                ugx_amount_efris=total * 3700,
                balance_due=total,
                status=status,
                due_date=today - timedelta(days=days_ago) + timedelta(days=due_days),
                created_by=admin,
            )

        prefix = f'DEMO-{today.year}'
        paid = note(f'{prefix}-001', 'Sanitas Seguros', '4200', '756', 70, 30, 'sent')
        partial = note(f'{prefix}-002', 'Andina Salud', '6500', '1170', 40, 30, 'sent')
        note(f'{prefix}-003', 'Sanitas Seguros', '3100', '558', 25, 30, 'sent')
        note(f'{prefix}-004', 'Andina Salud', '2800', '504', 95, 30, 'sent')
        note(f'{prefix}-005', 'Norte Vida', '5400', '972', 3, 30, 'submitted')
        note(f'{prefix}-006', 'Norte Vida', '1900', '342', 0, 30, 'draft')
        update = FeeNote.objects.filter(tenant=tenant, fee_note_number=f'{prefix}-004')
        update.update(status='overdue_3')
        pay_day = today - timedelta(days=5)
        PaymentService.record_payment(
            paid,
            {
                'payment_date': pay_day,
                'payment_method': 'bank_transfer',
                'bank_reference': 'TRX-88231',
                'amount_received_foreign': paid.balance_due,
                'payment_currency': 'USD',
                'exchange_rate': Decimal('3720'),
                'wht_deducted': True,
                'wht_amount': Decimal('252.00'),
                'wht_cert_number': 'WHT-2026-114',
            },
            admin,
        )
        PaymentService.record_payment(
            partial,
            {
                'payment_date': pay_day,
                'payment_method': 'cheque',
                'bank_reference': 'CHQ-0045',
                'amount_received_foreign': Decimal('3000'),
                'payment_currency': 'USD',
                'exchange_rate': Decimal('3690'),
                'wht_deducted': False,
                'wht_amount': Decimal('0'),
            },
            admin,
        )

    def seed_payroll(self, tenant, today, admin):
        User = get_user_model()
        staff = [
            ('Ana Pérez', '2400000', 'transport', '150000'),
            ('Luis Gómez', '3200000', 'housing', '400000'),
            ('Rosa Mendoza', '1800000', 'lunch', '90000'),
            ('Carlos Rivas', '5200000', 'medical', '250000'),
        ]
        for index, (name, salary, allowance, amount) in enumerate(staff, start=1):
            user, _ = User.objects.get_or_create(
                username=f'demo_empleado{index}', defaults={'first_name': name.split()[0], 'last_name': name.split()[1]}
            )
            if not user.has_usable_password():
                user.set_unusable_password()
                user.save(update_fields=['password'])
            UserTenantRole.objects.get_or_create(tenant=tenant, user=user, defaults={'role': 'viewer'})
            profile = EmployeePayrollProfile.objects.create(
                tenant=tenant,
                user=user,
                employee_number=f'E{index:03d}',
                tin_number=f'100{index}2345',
                nssf_number=f'NS{index}7788',
                bank_name='Banco Nacional',
                bank_account_number=f'00{index}-5521',
                gross_salary=Decimal(salary),
                start_date=date(today.year - 1, 1, 1),
            )
            EmployeeAllowance.objects.create(
                employee=profile, allowance_type=allowance, amount=Decimal(amount), is_taxable=allowance != 'medical'
            )
        first_of_month = today.replace(day=1)
        for back in (2, 1):
            month_start = (first_of_month - timedelta(days=30 * back)).replace(day=1)
            run = PayrollService.run_monthly_payroll(tenant, month_start.month, month_start.year, admin)
            run.status = 'paid' if back == 2 else 'approved'
            run.approved_by, run.approved_at = admin, timezone.now()
            run.save()
        PayrollService.run_monthly_payroll(tenant, today.month, today.year, admin)

    def seed_treasury(self, tenant, today):
        def account(name, bank, number, currency, kind, opening):
            return BankAccount.objects.create(
                tenant=tenant,
                account_name=name,
                bank_name=bank,
                account_number=number,
                currency=currency,
                account_type=kind,
                opening_balance=Decimal(opening),
                current_balance=Decimal(opening),
            )

        main = account('Cuenta operativa USD', 'Banco Nacional', '001-884-221', 'USD', 'current', '42000')
        account('Ahorros operativos', 'Banco Nacional', '001-884-990', 'USD', 'savings', '15000')
        box = account('Caja chica oficina', 'Efectivo', 'CAJA-1', 'USD', 'petty_cash', '600')
        for days, kind, amount, text in (
            (12, 'withdrawal', '45.50', 'Papelería urgente'),
            (9, 'withdrawal', '120.00', 'Mensajería y transporte'),
            (6, 'withdrawal', '38.75', 'Café y agua para visitas'),
            (2, 'top_up', '200.00', 'Reposición de caja'),
        ):
            PettyCashTransaction.objects.create(
                tenant=tenant,
                bank_account=box,
                transaction_type=kind,
                amount=Decimal(amount),
                description=text,
                transaction_date=today - timedelta(days=days),
                reference=f'CC-{days:03d}',
            )
            box.current_balance += Decimal(amount) * (1 if kind == 'top_up' else -1)
        box.save(update_fields=['current_balance'])

        def cheque(number, kind, amount, who, days, status):
            item = Cheque.objects.create(
                tenant=tenant,
                bank_account=main,
                cheque_type=kind,
                cheque_number=number,
                amount=Decimal(amount),
                payee_payer=who,
                issue_date=today - timedelta(days=days),
                status=status,
                cleared_date=today - timedelta(days=days - 3) if status == 'cleared' else None,
            )
            if status == 'cleared':
                main.current_balance += Decimal(amount) * (1 if kind == 'receipt' else -1)
            return item

        cheque('000145', 'issued', '1800.00', 'Proveedor de oficina', 20, 'cleared')
        cheque('000146', 'issued', '950.00', 'Servicios legales', 4, 'pending')
        cheque('A-7781', 'receipt', '3000.00', 'Andina Salud', 6, 'pending')
        cheque('000144', 'issued', '420.00', 'Mantenimiento', 30, 'bounced')
        main.save(update_fields=['current_balance'])
        last = today.replace(day=1) - timedelta(days=1)
        BankReconciliation.objects.create(
            tenant=tenant,
            bank_account=main,
            period_month=last.month,
            period_year=last.year,
            opening_balance=Decimal('42000'),
            closing_balance_per_bank=main.current_balance + Decimal('950'),
            closing_balance_per_system=main.current_balance,
            notes='Cheque 000146 aún sin cobrar.',
        )

    def seed_accounting(self, tenant, today, admin):
        spec = [
            ('1000', 'Caja y bancos', 'asset'),
            ('1100', 'Cuentas por cobrar', 'asset'),
            ('2000', 'Cuentas por pagar', 'liability'),
            ('2100', 'Impuestos por pagar', 'liability'),
            ('3000', 'Capital', 'equity'),
            ('4000', 'Ingresos por honorarios', 'income'),
            ('5000', 'Sueldos y salarios', 'expense'),
            ('5100', 'Alquiler', 'expense'),
            ('5200', 'Servicios básicos', 'expense'),
        ]
        accounts = {
            code: Account.objects.create(tenant=tenant, code=code, name=name, category=category)
            for code, name, category in spec
        }

        def entry(days, ref, text, lines):
            item = JournalEntry.objects.create(
                tenant=tenant,
                entry_date=today - timedelta(days=days),
                reference=ref,
                description=text,
                created_by=admin,
            )
            for code, debit, credit in lines:
                JournalLine.objects.create(
                    tenant=tenant,
                    journal_entry=item,
                    account=accounts[code],
                    debit_amount=Decimal(debit),
                    credit_amount=Decimal(credit),
                )

        entry(40, 'AS-001', 'Cobro de honorarios', [('1000', '8000', '0'), ('4000', '0', '8000')])
        entry(25, 'AS-002', 'Pago de alquiler', [('5100', '2000', '0'), ('1000', '0', '2000')])
        entry(18, 'AS-003', 'Nómina del mes', [('5000', '6500', '0'), ('1000', '0', '6500')])
        entry(10, 'AS-004', 'Honorarios facturados', [('1100', '11700', '0'), ('4000', '0', '11700')])
        entry(6, 'AS-005', 'Electricidad y agua', [('5200', '480', '0'), ('1000', '0', '480')])
