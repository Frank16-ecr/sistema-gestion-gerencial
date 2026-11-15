"""Carga una empresa de ejemplo para ver el panel con datos: python manage.py seed_demo"""
import random
from datetime import date
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from finance.budgets.models import Budget, BudgetLine
from finance.expenses.models import Expense
from finance.investments.models import Investment, InvestmentMovement
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
    'rent': 'Alquiler de oficina', 'utilities': 'Electricidad y agua', 'internet': 'Plan de internet',
    'travel': 'Viaje de visita a clientes', 'office_supplies': 'Papelería y suministros', 'fuel': 'Combustible',
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
                self.stdout.write(self.style.WARNING(
                    'La empresa de ejemplo ya existe. Usa --reset para recrearla.'))
                return
            existing.delete()

        rng = random.Random(42)  # datos repetibles
        today = timezone.localdate()
        year = today.year
        tenant = Tenant.objects.create(name='Empresa Demo', slug=SLUG)

        budget = Budget.objects.create(
            tenant=tenant, name='Presupuesto operativo', fiscal_year=year, status='approved',
            period_start=date(year, 1, 1), period_end=date(year, 12, 31), currency='USD',
            approved_at=timezone.now(), notes='Presupuesto de ejemplo generado por seed_demo.',
        )
        for category, (planned, _monthly) in PLAN.items():
            BudgetLine.objects.create(budget=budget, category=category, planned_amount=Decimal(planned))
        Budget.objects.create(
            tenant=tenant, name='Plan de capacitación', fiscal_year=year, status='draft',
            period_start=date(year, 1, 1), period_end=date(year, 12, 31), currency='USD',
        )

        expenses = 0
        for month in range(1, today.month + 1):
            for category, (_planned, monthly) in PLAN.items():
                amount = Decimal(monthly) * Decimal(rng.uniform(0.8, 1.25)).quantize(Decimal('0.01'))
                last_month = month == today.month
                status = 'pending' if last_month and category in ('travel', 'fuel') else 'paid'
                max_day = today.day if last_month else 28  # nunca fechas futuras
                Expense.objects.create(
                    tenant=tenant, description=DESCRIPTIONS[category], category=category,
                    amount=amount.quantize(Decimal('0.01')), currency='USD',
                    expense_date=date(year, month, rng.randint(1, max_day)), status=status,
                )
                expenses += 1
        # Un gasto fuera del presupuesto y uno rechazado, para ver esos casos.
        Expense.objects.create(tenant=tenant, description='Multa administrativa', category='other',
                               amount=Decimal('320.00'), currency='USD', expense_date=date(year, 3, 12), status='paid')
        Expense.objects.create(tenant=tenant, description='Cena de equipo', category='other',
                               amount=Decimal('180.00'), currency='USD', expense_date=date(year, 4, 2),
                               status='rejected')

        deposito = Investment.objects.create(
            tenant=tenant, name='Depósito a plazo', asset_type='term_deposit', institution='Banco Central',
            initial_amount=Decimal('50000'), start_date=date(year, 1, 15), maturity_date=date(year + 1, 1, 15),
            expected_return_rate=Decimal('6.5'), currency='USD',
        )
        fondo = Investment.objects.create(
            tenant=tenant, name='Fondo de renta fija', asset_type='fund', institution='Fondo Andino',
            initial_amount=Decimal('20000'), start_date=date(year, 2, 1), expected_return_rate=Decimal('4.2'),
            currency='EUR',
        )
        bonos = Investment.objects.create(
            tenant=tenant, name='Bonos corporativos', asset_type='bond', institution='Mesa de dinero',
            initial_amount=Decimal('15000'), start_date=date(year, 3, 1), maturity_date=date(year + 2, 3, 1),
            expected_return_rate=Decimal('7.8'), currency='USD',
        )
        moves = [
            (deposito, 'contribution', '10000', 3), (deposito, 'return', '1250', 6),
            (deposito, 'withdrawal', '2000', 8), (deposito, 'fee', '45', 8),
            (fondo, 'return', '310', 5), (fondo, 'return', '295', 8), (fondo, 'fee', '25', 8),
            (bonos, 'return', '585', 6), (bonos, 'return', '585', 9),
        ]
        for investment, kind, amount, month in moves:
            if month <= today.month:
                InvestmentMovement.objects.create(
                    investment=investment, movement_type=kind, amount=Decimal(amount),
                    movement_date=date(year, month, 1),
                )

        self.stdout.write(self.style.SUCCESS(
            f'Listo: "Empresa Demo" con 2 presupuestos, {expenses + 2} gastos y 3 inversiones.'))
        self.stdout.write('Si eres superusuario, ya la ves en el panel. '
                          'Un usuario normal necesita un rol en esa empresa.')
