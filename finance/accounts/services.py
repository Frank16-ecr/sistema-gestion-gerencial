"""Asientos contables automaticos.

Los modulos (facturacion, cobros, nomina) no usan codigos de cuenta fijos sino
*roles* ("receivables", "vat_debit"...). Cada rol apunta a un codigo del plan de
cuentas de la empresa; el mapeo por defecto corresponde al plan basico que crea
`python manage.py crear_plan_cuentas`, y puede cambiarse con el TenantSetting
`account_mapping` ({"rol": "codigo"}).

Todos los importes de los asientos estan en la moneda base de la empresa (en
Venezuela, bolivares); el importe y la tasa en divisas se guardan como referencia.
"""
from decimal import Decimal

from django.db import transaction

from tenants.config import get_tenant_setting

ACCOUNT_MAPPING_KEY = 'account_mapping'
AUTO_JOURNAL_KEY = 'auto_journal'
CENT = Decimal('0.01')

# Plan de cuentas basico (Venezuela, VEN-NIF). (codigo, nombre, categoria, padre)
VENEZUELA_CHART = [
    ('1', 'ACTIVO', 'asset', None),
    ('1.1', 'Activo corriente', 'asset', '1'),
    ('1.1.01', 'Caja', 'asset', '1.1'),
    ('1.1.02', 'Bancos', 'asset', '1.1'),
    ('1.1.03', 'Cuentas por cobrar clientes', 'asset', '1.1'),
    ('1.1.04', 'IVA credito fiscal', 'asset', '1.1'),
    ('1.1.05', 'IVA retenido por clientes', 'asset', '1.1'),
    ('1.1.06', 'Anticipos de ISLR', 'asset', '1.1'),
    ('2', 'PASIVO', 'liability', None),
    ('2.1', 'Pasivo corriente', 'liability', '2'),
    ('2.1.01', 'Cuentas por pagar proveedores', 'liability', '2.1'),
    ('2.1.02', 'IVA debito fiscal', 'liability', '2.1'),
    ('2.1.03', 'IGTF percibido por pagar', 'liability', '2.1'),
    ('2.1.04', 'Sueldos y salarios por pagar', 'liability', '2.1'),
    ('2.1.05', 'Retenciones de ISLR por pagar', 'liability', '2.1'),
    ('2.1.06', 'Aportes y contribuciones de nomina por pagar', 'liability', '2.1'),
    ('3', 'PATRIMONIO', 'equity', None),
    ('3.1.01', 'Capital social', 'equity', '3'),
    ('3.2.01', 'Resultados acumulados', 'equity', '3'),
    ('4', 'INGRESOS', 'income', None),
    ('4.1.01', 'Ventas y prestacion de servicios', 'income', '4'),
    ('4.1.02', 'Devoluciones y descuentos en ventas', 'income', '4'),
    ('4.2.01', 'Ganancia por diferencial cambiario', 'income', '4'),
    ('5', 'GASTOS', 'expense', None),
    ('5.1.01', 'Sueldos y salarios', 'expense', '5'),
    ('5.1.02', 'Aportes patronales y contribuciones', 'expense', '5'),
    ('5.2.01', 'Perdida por diferencial cambiario', 'expense', '5'),
    ('5.3.01', 'Gastos generales', 'expense', '5'),
]

DEFAULT_ACCOUNT_MAPPING = {
    'cash': '1.1.01',
    'bank': '1.1.02',
    'receivables': '1.1.03',
    'vat_credit': '1.1.04',
    'vat_withheld_by_customers': '1.1.05',
    'vat_debit': '2.1.02',
    'igtf_payable': '2.1.03',
    'salaries_payable': '2.1.04',
    'income_tax_withheld_payable': '2.1.05',
    'payroll_contributions_payable': '2.1.06',
    'sales': '4.1.01',
    'sales_returns': '4.1.02',
    'fx_gain': '4.2.01',
    'salaries_expense': '5.1.01',
    'employer_contributions_expense': '5.1.02',
    'fx_loss': '5.2.01',
}


class AccountingConfigError(ValueError):
    """Falta una cuenta del plan o el asiento no cuadra."""


def auto_journal_enabled(tenant):
    return bool(get_tenant_setting(tenant, AUTO_JOURNAL_KEY, True))


def create_chart_of_accounts(tenant, chart=VENEZUELA_CHART):
    """Crea (si faltan) las cuentas del plan basico. Devuelve cuantas se crearon."""
    from .models import Account

    created = 0
    for code, name, category, parent_code in chart:
        parent = Account.objects.get(tenant=tenant, code=parent_code) if parent_code else None
        _, was_created = Account.objects.get_or_create(
            tenant=tenant, code=code, defaults={'name': name, 'category': category, 'parent': parent},
        )
        created += was_created
    return created


def get_account(tenant, role):
    from .models import Account

    mapping = {**DEFAULT_ACCOUNT_MAPPING, **(get_tenant_setting(tenant, ACCOUNT_MAPPING_KEY, {}) or {})}
    code = mapping.get(role)
    if code is None:
        raise AccountingConfigError(f'No hay cuenta asignada al rol contable "{role}".')
    try:
        return Account.objects.get(tenant=tenant, code=code, is_active=True)
    except Account.DoesNotExist:
        raise AccountingConfigError(
            f'Falta la cuenta {code} (rol "{role}") en el plan de cuentas de {tenant}. '
            f'Ejecuta "python manage.py crear_plan_cuentas {tenant.slug}" o ajusta account_mapping.'
        )


def money(value):
    return Decimal(value).quantize(CENT)


@transaction.atomic
def post_entry(tenant, entry_date, lines, reference='', description='', user=None):
    """Registra un asiento cuadrado.

    `lines`: lista de dicts {role, debit, credit, description?, foreign_currency?,
    foreign_amount?, exchange_rate?}. Las lineas con importe cero se omiten.
    Devuelve el JournalEntry, o None si la empresa desactivo los asientos automaticos.
    """
    from .models import JournalEntry, JournalLine

    if not auto_journal_enabled(tenant):
        return None
    prepared = []
    for line in lines:
        debit, credit = money(line.get('debit', 0)), money(line.get('credit', 0))
        if debit < 0 or credit < 0:
            raise AccountingConfigError('Los importes de un asiento no pueden ser negativos.')
        if debit == 0 and credit == 0:
            continue
        prepared.append((get_account(tenant, line['role']), debit, credit, line))
    total_debit = sum((p[1] for p in prepared), Decimal('0'))
    total_credit = sum((p[2] for p in prepared), Decimal('0'))
    if not prepared:
        return None
    if total_debit != total_credit:
        raise AccountingConfigError(f'El asiento no cuadra: debe {total_debit} / haber {total_credit}.')

    entry = JournalEntry.objects.create(
        tenant=tenant, entry_date=entry_date, reference=reference[:100], description=description,
        created_by_system=True, created_by=user,
    )
    for account, debit, credit, line in prepared:
        JournalLine.objects.create(
            tenant=tenant, journal_entry=entry, account=account, debit_amount=debit, credit_amount=credit,
            description=line.get('description', ''), foreign_currency=line.get('foreign_currency'),
            foreign_amount=line.get('foreign_amount'), exchange_rate=line.get('exchange_rate'),
        )
    return entry


@transaction.atomic
def reverse_entry(entry, entry_date, reason='', user=None):
    """Asiento inverso (para anulaciones): intercambia debe y haber."""
    from .models import JournalEntry, JournalLine

    if entry is None:
        return None
    reversal = JournalEntry.objects.create(
        tenant=entry.tenant, entry_date=entry_date, reference=f'REV-{entry.reference}'[:100],
        description=f'Reverso de {entry.reference}. {reason}'.strip(), created_by_system=True, created_by=user,
    )
    for line in entry.lines.all():
        JournalLine.objects.create(
            tenant=entry.tenant, journal_entry=reversal, account=line.account,
            debit_amount=line.credit_amount, credit_amount=line.debit_amount, description=line.description,
            foreign_currency=line.foreign_currency, foreign_amount=line.foreign_amount,
            exchange_rate=line.exchange_rate,
        )
    return reversal
