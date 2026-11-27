"""Logica de facturacion venezolana: calculo de IVA, emision, cobros con IGTF,
retenciones de IVA, anulacion y obligaciones fiscales del mes."""
import calendar
from datetime import date
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from finance.accounts.services import money, post_entry, reverse_entry
from finance.fx.services import ExchangeRateNotFound, get_rate
from tenants.config import get_tenant_setting

ZERO = Decimal('0')
HUNDRED = Decimal('100')

VAT_RATES_KEY = 'vat_rates'
IGTF_RATE_KEY = 'igtf_rate'
TAX_CALENDAR_KEY = 'tax_calendar'

# Alicuotas vigentes (Ley del IVA). Configurables por empresa con TenantSetting 'vat_rates'.
DEFAULT_VAT_RATES = {'general': 16, 'reduced': 8, 'luxury_additional': 15}
DEFAULT_IGTF_RATE = 3
DEFAULT_TAX_CALENDAR = {'iva_due_day': 15, 'igtf_due_day': 15}

LOCAL_CURRENCY = 'VES'


class InvoiceError(ValueError):
    """Operacion de facturacion no permitida."""


def vat_rates(tenant):
    rates = {**DEFAULT_VAT_RATES, **(get_tenant_setting(tenant, VAT_RATES_KEY, {}) or {})}
    return {k: Decimal(str(v)) for k, v in rates.items()}


def igtf_rate(tenant):
    return Decimal(str(get_tenant_setting(tenant, IGTF_RATE_KEY, DEFAULT_IGTF_RATE)))


def category_rate(rates, category):
    if category == 'general':
        return rates['general']
    if category == 'reduced':
        return rates['reduced']
    if category == 'luxury':
        return rates['general'] + rates['luxury_additional']
    return ZERO


def to_ves(amount, rate):
    return money(Decimal(amount) * Decimal(rate))


def _rate_to_ves(tenant, currency, on_date):
    try:
        return get_rate(tenant, currency, LOCAL_CURRENCY, on_date)
    except ExchangeRateNotFound as exc:
        raise InvoiceError(f'{exc} Ejecuta "actualizar_tasa_bcv" o registra la tasa manualmente.')


# ---------------------------------------------------------------------------
# Calculo
# ---------------------------------------------------------------------------

def recalculate(invoice, rates=None):
    """Recalcula bases, impuestos y totales a partir de las lineas."""
    rates = rates or vat_rates(invoice.tenant)
    bases = dict.fromkeys(('general', 'reduced', 'luxury', 'exempt'), ZERO)
    for line in invoice.lines.all():
        gross = Decimal(line.quantity) * Decimal(line.unit_price)
        line_base = money(gross * (HUNDRED - Decimal(line.discount_percent)) / HUNDRED)
        if line.line_base != line_base:
            line.line_base = line_base
            line.save(update_fields=['line_base'])
        bases[line.tax_category] += line_base

    invoice.exempt_amount = bases['exempt']
    invoice.base_general = bases['general']
    invoice.base_reduced = bases['reduced']
    invoice.base_luxury = bases['luxury']
    invoice.tax_general = money(bases['general'] * category_rate(rates, 'general') / HUNDRED)
    invoice.tax_reduced = money(bases['reduced'] * category_rate(rates, 'reduced') / HUNDRED)
    invoice.tax_luxury = money(bases['luxury'] * category_rate(rates, 'luxury') / HUNDRED)
    invoice.subtotal = sum(bases.values(), ZERO)
    invoice.tax_total = invoice.tax_general + invoice.tax_reduced + invoice.tax_luxury
    invoice.total = invoice.subtotal + invoice.tax_total
    invoice.vat_rates = {k: str(v) for k, v in rates.items()}
    invoice.balance_due = invoice.total if invoice.status == 'draft' else invoice.balance_due
    invoice.save()
    return invoice


def _next_number(tenant, doc_type):
    from .models import DocumentSequence

    seq, _ = DocumentSequence.objects.select_for_update().get_or_create(tenant=tenant, doc_type=doc_type)
    seq.last_number += 1
    seq.save(update_fields=['last_number'])
    return seq.last_number


def _update_status(invoice):
    settled = invoice.amount_paid + invoice.vat_withheld + invoice.credited
    if invoice.status == 'void':
        return
    if invoice.balance_due <= Decimal('0.00'):
        invoice.status = 'paid'
    elif settled > 0:
        invoice.status = 'partial'
    else:
        invoice.status = 'issued'


# ---------------------------------------------------------------------------
# Emision y anulacion
# ---------------------------------------------------------------------------

@transaction.atomic
def issue_invoice(invoice, user=None):
    """Emite el documento: asigna numero y numero de control, fija la tasa BCV,
    congela los datos del cliente, registra el asiento y actualiza el IVA del mes."""
    from .models import Invoice, TaxpayerProfile

    invoice = Invoice.objects.select_for_update().get(pk=invoice.pk)
    if invoice.status != 'draft':
        raise InvoiceError('Solo se emiten documentos en borrador.')
    if not TaxpayerProfile.objects.filter(tenant=invoice.tenant).exists():
        raise InvoiceError('Registra primero los datos fiscales de la empresa (RIF y razon social).')
    if not invoice.lines.exists():
        raise InvoiceError('El documento no tiene lineas.')
    if invoice.customer.tenant_id != invoice.tenant_id:
        raise InvoiceError('El cliente pertenece a otra empresa.')

    related = invoice.related_invoice
    if invoice.doc_type in ('credit_note', 'debit_note'):
        if related is None or related.doc_type != 'invoice' or related.status in ('draft', 'void'):
            raise InvoiceError('Las notas deben afectar una factura emitida y no anulada.')
        if related.customer_id != invoice.customer_id or related.currency != invoice.currency:
            raise InvoiceError('La nota debe tener el mismo cliente y moneda que la factura afectada.')
    elif related is not None:
        raise InvoiceError('Una factura no puede afectar a otra factura.')

    recalculate(invoice)
    if invoice.total <= 0:
        raise InvoiceError('El total del documento debe ser mayor que cero.')
    if invoice.doc_type == 'credit_note':
        related = Invoice.objects.select_for_update().get(pk=related.pk)
        if invoice.total > related.balance_due:
            raise InvoiceError(
                f'La nota de credito ({invoice.total}) supera el saldo de la factura ({related.balance_due}).'
            )

    invoice.exchange_rate = _rate_to_ves(invoice.tenant, invoice.currency, invoice.issue_date)
    invoice.number = f'{_next_number(invoice.tenant, invoice.doc_type):08d}'
    invoice.control_number = f'00-{_next_number(invoice.tenant, "control"):08d}'
    customer = invoice.customer
    invoice.customer_rif, invoice.customer_name = customer.rif, customer.name
    invoice.customer_address = customer.fiscal_address
    invoice.status = 'issued'
    invoice.issued_at = timezone.now()
    invoice.issued_by = user

    if invoice.doc_type == 'credit_note':
        invoice.balance_due = ZERO
        related.credited += invoice.total
        related.balance_due -= invoice.total
        _update_status(related)
        related.save()
    else:
        invoice.balance_due = invoice.total
    invoice.journal_entry = _post_invoice(invoice, user)
    invoice.save()
    refresh_tax_obligations(invoice.tenant, invoice.issue_date.year, invoice.issue_date.month)
    return invoice


def _post_invoice(invoice, user):
    rate = invoice.exchange_rate
    total_ves = to_ves(invoice.total, rate)
    tax_ves = to_ves(invoice.tax_total, rate)
    income_ves = total_ves - tax_ves  # evita descuadres por redondeo
    fx = {'foreign_currency': invoice.currency, 'exchange_rate': rate} if invoice.currency != LOCAL_CURRENCY else {}
    label = f'{invoice.get_doc_type_display()} {invoice.number}'
    if invoice.doc_type == 'credit_note':
        lines = [
            {'role': 'sales_returns', 'debit': income_ves, **fx},
            {'role': 'vat_debit', 'debit': tax_ves},
            {'role': 'receivables', 'credit': total_ves, 'foreign_amount': invoice.total, **fx},
        ]
    else:
        lines = [
            {'role': 'receivables', 'debit': total_ves, 'foreign_amount': invoice.total, **fx},
            {'role': 'sales', 'credit': income_ves, **fx},
            {'role': 'vat_debit', 'credit': tax_ves},
        ]
    return post_entry(invoice.tenant, invoice.issue_date, lines, reference=label,
                      description=f'{label} - {invoice.customer_name}', user=user)


@transaction.atomic
def void_invoice(invoice, reason, user=None, void_date=None):
    """Anula un documento emitido sin cobros. Conserva su numeracion (no se borra)."""
    from .models import Invoice

    invoice = Invoice.objects.select_for_update().get(pk=invoice.pk)
    if invoice.status in ('draft', 'void'):
        raise InvoiceError('Solo se anulan documentos emitidos.')
    if not reason:
        raise InvoiceError('Indica el motivo de la anulacion.')
    if invoice.payments.exists() or invoice.vat_withholdings.exists():
        raise InvoiceError('El documento tiene cobros o retenciones: emite una nota de credito en su lugar.')
    if invoice.adjustment_notes.exclude(status='void').exists():
        raise InvoiceError('Anula primero las notas que afectan a esta factura.')

    void_date = void_date or timezone.localdate()
    if invoice.doc_type == 'credit_note' and invoice.related_invoice_id:
        related = Invoice.objects.select_for_update().get(pk=invoice.related_invoice_id)
        related.credited -= invoice.total
        related.balance_due += invoice.total
        _update_status(related)
        related.save()
    reverse_entry(invoice.journal_entry, void_date, reason, user)
    invoice.status = 'void'
    invoice.balance_due = ZERO
    invoice.void_reason = reason
    invoice.voided_at = timezone.now()
    invoice.save()
    refresh_tax_obligations(invoice.tenant, invoice.issue_date.year, invoice.issue_date.month)
    return invoice


# ---------------------------------------------------------------------------
# Cobros y retenciones
# ---------------------------------------------------------------------------

@transaction.atomic
def register_payment(invoice, payment_date, amount, currency, method='transfer', reference='', user=None):
    """Registra un cobro.

    - Convierte el pago a la moneda de la factura con la tasa BCV de la fecha del pago.
    - Si el pago es en divisas y la empresa es agente de percepcion, calcula el IGTF
      (3% por defecto) que el cliente paga adicionalmente.
    - El diferencial cambiario (tasa del pago vs. tasa de emision) va a ganancia o perdida.
    """
    from .models import Invoice, InvoicePayment, TaxpayerProfile

    invoice = Invoice.objects.select_for_update().get(pk=invoice.pk)
    if invoice.doc_type == 'credit_note':
        raise InvoiceError('Las notas de credito no se cobran.')
    if invoice.status not in ('issued', 'partial'):
        raise InvoiceError('Solo se registran cobros de documentos emitidos con saldo pendiente.')
    amount = money(amount)
    if amount <= 0:
        raise InvoiceError('El monto debe ser mayor que cero.')
    if payment_date < invoice.issue_date:
        raise InvoiceError('El pago no puede ser anterior a la emision.')

    tenant = invoice.tenant
    pay_rate = _rate_to_ves(tenant, currency, payment_date)
    amount_ves = to_ves(amount, pay_rate)
    if currency == invoice.currency:
        applied = amount
    else:
        invoice_rate_today = _rate_to_ves(tenant, invoice.currency, payment_date)
        applied = money(amount_ves / invoice_rate_today)
    if applied > invoice.balance_due + Decimal('0.01'):
        raise InvoiceError(f'El pago ({applied} {invoice.currency}) supera el saldo ({invoice.balance_due}).')
    applied = min(applied, invoice.balance_due)

    profile = TaxpayerProfile.objects.filter(tenant=tenant).first()
    rate_igtf = igtf_rate(tenant) if (currency != LOCAL_CURRENCY and profile and profile.igtf_collection_agent) \
        else ZERO
    igtf_amount = money(amount * rate_igtf / HUNDRED)
    igtf_ves = to_ves(igtf_amount, pay_rate)

    receivable_ves = to_ves(applied, invoice.exchange_rate)
    fx_difference = amount_ves - receivable_ves

    payment = InvoicePayment.objects.create(
        tenant=tenant, invoice=invoice, payment_date=payment_date, method=method, reference=reference,
        currency=currency, amount=amount, exchange_rate=pay_rate, amount_ves=amount_ves, applied_amount=applied,
        igtf_rate=rate_igtf, igtf_amount=igtf_amount, igtf_amount_ves=igtf_ves, fx_difference_ves=fx_difference,
        created_by=user,
    )
    fx_info = {'foreign_currency': currency, 'foreign_amount': amount + igtf_amount, 'exchange_rate': pay_rate} \
        if currency != LOCAL_CURRENCY else {}
    lines = [
        {'role': 'bank', 'debit': amount_ves + igtf_ves, **fx_info},
        {'role': 'receivables', 'credit': receivable_ves},
        {'role': 'igtf_payable', 'credit': igtf_ves},
    ]
    if fx_difference > 0:
        lines.append({'role': 'fx_gain', 'credit': fx_difference})
    elif fx_difference < 0:
        lines.append({'role': 'fx_loss', 'debit': -fx_difference})
    payment.journal_entry = post_entry(
        tenant, payment_date, lines, reference=f'Cobro {invoice.number}',
        description=f'Cobro de {invoice} ({reference})'.strip(), user=user,
    )
    payment.save(update_fields=['journal_entry'])

    invoice.amount_paid += applied
    invoice.balance_due -= applied
    _update_status(invoice)
    invoice.save()
    refresh_tax_obligations(tenant, payment_date.year, payment_date.month)
    return payment


@transaction.atomic
def register_vat_withholding(invoice, voucher_number, voucher_date, percent=None, user=None):
    """Registra el comprobante de retencion de IVA que entrega un cliente contribuyente especial."""
    from .models import Invoice, VatWithholding

    invoice = Invoice.objects.select_for_update().get(pk=invoice.pk)
    if invoice.doc_type != 'invoice' or invoice.status not in ('issued', 'partial', 'paid'):
        raise InvoiceError('Las retenciones se registran sobre facturas emitidas.')
    if invoice.vat_withholdings.exists():
        raise InvoiceError('La factura ya tiene un comprobante de retencion.')
    percent = int(percent or invoice.customer.vat_withholding_percent)
    if percent not in (75, 100):
        raise InvoiceError('La retencion de IVA es del 75% o del 100%.')
    amount = money(invoice.tax_total * percent / HUNDRED)
    if amount > invoice.balance_due:
        raise InvoiceError('La retencion supera el saldo pendiente: registrala antes del cobro total.')
    amount_ves = to_ves(amount, invoice.exchange_rate)
    withholding = VatWithholding.objects.create(
        tenant=invoice.tenant, invoice=invoice, voucher_number=voucher_number, voucher_date=voucher_date,
        percent=percent, amount=amount, amount_ves=amount_ves,
    )
    withholding.journal_entry = post_entry(
        invoice.tenant, voucher_date,
        [{'role': 'vat_withheld_by_customers', 'debit': amount_ves}, {'role': 'receivables', 'credit': amount_ves}],
        reference=f'Ret. IVA {voucher_number}', description=f'Retencion de IVA sobre {invoice}', user=user,
    )
    withholding.save(update_fields=['journal_entry'])
    invoice.vat_withheld += amount
    invoice.balance_due -= amount
    _update_status(invoice)
    invoice.save()
    refresh_tax_obligations(invoice.tenant, voucher_date.year, voucher_date.month)
    return withholding


# ---------------------------------------------------------------------------
# Libro de ventas y obligaciones
# ---------------------------------------------------------------------------

def sales_book(tenant, year, month):
    """Libro de ventas del mes, en bolivares (las notas de credito restan)."""
    from .models import Invoice

    docs = (
        Invoice.objects.filter(tenant=tenant, issue_date__year=year, issue_date__month=month)
        .exclude(status='draft')
        .select_related('related_invoice')
        .prefetch_related('vat_withholdings')
        .order_by('issue_date', 'control_number')
    )
    rows = []
    totals = dict.fromkeys(
        ('total', 'exempt', 'base_general', 'tax_general', 'base_reduced', 'tax_reduced',
         'base_luxury', 'tax_luxury', 'vat_withheld'), ZERO)
    for i, doc in enumerate(docs, start=1):
        rate = doc.exchange_rate
        voided = doc.status == 'void'
        sign = 0 if voided else doc.sign

        def bs(value, sign=sign, rate=rate):
            return to_ves(value, rate) * sign

        withholding = doc.vat_withholdings.first()
        row = {
            'line': i,
            'date': doc.issue_date,
            'doc_type': doc.get_doc_type_display(),
            'number': doc.number,
            'control_number': doc.control_number,
            'customer_rif': doc.customer_rif,
            'customer_name': doc.customer_name,
            'affected_invoice': doc.related_invoice.number if doc.related_invoice else '',
            'status': 'ANULADA' if voided else '',
            'currency': doc.currency,
            'exchange_rate': rate,
            'total': bs(doc.total),
            'exempt': bs(doc.exempt_amount),
            'base_general': bs(doc.base_general),
            'tax_general': bs(doc.tax_general),
            'base_reduced': bs(doc.base_reduced),
            'tax_reduced': bs(doc.tax_reduced),
            'base_luxury': bs(doc.base_luxury),
            'tax_luxury': bs(doc.tax_luxury),
            'vat_withheld': withholding.amount_ves if withholding and not voided else ZERO,
            'withholding_voucher': withholding.voucher_number if withholding else '',
        }
        for key in totals:
            totals[key] += row[key]
        rows.append(row)
    totals['tax_total'] = totals['tax_general'] + totals['tax_reduced'] + totals['tax_luxury']
    return {'year': year, 'month': month, 'rows': rows, 'totals': totals}


def _due_date(year, month, day):
    next_month, next_year = (month + 1, year) if month < 12 else (1, year + 1)
    return date(next_year, next_month, min(int(day), calendar.monthrange(next_year, next_month)[1]))


def refresh_tax_obligations(tenant, year, month):
    """Actualiza las obligaciones de IVA e IGTF del mes.

    IVA a pagar = debito fiscal del libro de ventas - retenciones recibidas en el mes.
    (El credito fiscal de compras se descuenta en la declaracion; este modulo no
    lleva libro de compras.)
    IGTF = IGTF percibido en los cobros del mes.
    """
    from finance.statutory.models import StatutoryObligation

    from .models import InvoicePayment, VatWithholding

    cal = {**DEFAULT_TAX_CALENDAR, **(get_tenant_setting(tenant, TAX_CALENDAR_KEY, {}) or {})}
    book = sales_book(tenant, year, month)
    withheld = VatWithholding.objects.filter(
        tenant=tenant, voucher_date__year=year, voucher_date__month=month,
    ).exclude(invoice__status='void').aggregate(t=Sum('amount_ves'))['t'] or ZERO
    vat_due = book['totals']['tax_total'] - withheld
    igtf_due = InvoicePayment.objects.filter(
        tenant=tenant, payment_date__year=year, payment_date__month=month,
    ).aggregate(t=Sum('igtf_amount_ves'))['t'] or ZERO

    for code, amount, due_day in (('iva', vat_due, cal['iva_due_day']), ('igtf', igtf_due, cal['igtf_due_day'])):
        existing = StatutoryObligation.objects.filter(
            tenant=tenant, obligation_type=code, period_month=month, period_year=year,
        ).first()
        if existing and existing.status in ('filed', 'paid'):
            continue  # ya declarada: no se toca
        if amount <= 0:
            if existing:
                existing.delete()
            continue
        StatutoryObligation.objects.update_or_create(
            tenant=tenant, obligation_type=code, period_month=month, period_year=year,
            defaults={'amount_due': money(amount), 'due_date': _due_date(year, month, due_day), 'status': 'pending'},
        )
