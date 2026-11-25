"""Facturacion segun la normativa venezolana.

Referencias: Providencia SNAT/2011/00071 (emision de facturas: numero de
factura y numero de control consecutivos, RIF, alicuotas discriminadas,
equivalente en bolivares de operaciones en divisas), Ley del IVA (alicuota
general, reducida y adicional por bienes suntuarios), retenciones de IVA de
contribuyentes especiales (Providencia SNAT/2015/0049) y Ley de Impuesto a las
Grandes Transacciones Financieras (IGTF sobre pagos en divisas percibido por
contribuyentes especiales).

Los documentos emitidos no se borran ni se modifican: se anulan o se corrigen
con notas de credito o debito.
"""
from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models

RIF_VALIDATOR = RegexValidator(
    r'^[VEJPGC]-\d{8}-\d$',
    'RIF invalido. Formato: letra (V, E, J, P, G o C), 8 digitos y digito verificador, p. ej. J-12345678-9.',
)

MONEY = {'max_digits': 18, 'decimal_places': 2, 'default': 0}


class TaxpayerProfile(models.Model):
    """Datos fiscales de la empresa emisora."""

    tenant = models.OneToOneField('tenants.Tenant', on_delete=models.CASCADE, related_name='taxpayer_profile')
    rif = models.CharField(max_length=12, validators=[RIF_VALIDATOR])
    legal_name = models.CharField('razon social', max_length=255)
    fiscal_address = models.TextField('domicilio fiscal')
    phone = models.CharField(max_length=50, blank=True)
    is_special_taxpayer = models.BooleanField('contribuyente especial', default=False)
    igtf_collection_agent = models.BooleanField(
        'agente de percepcion del IGTF', default=False,
        help_text='Si cobra IGTF sobre los pagos recibidos en divisas (contribuyentes especiales).',
    )
    vat_withholding_agent = models.BooleanField('agente de retencion de IVA', default=False)

    def __str__(self):
        return f'{self.legal_name} ({self.rif})'


class Customer(models.Model):
    VAT_WITHHOLDING_CHOICES = [(0, 'No retiene'), (75, '75%'), (100, '100%')]

    tenant = models.ForeignKey('tenants.Tenant', on_delete=models.CASCADE, related_name='customers')
    rif = models.CharField('RIF / cedula', max_length=12, validators=[RIF_VALIDATOR])
    name = models.CharField('nombre o razon social', max_length=255)
    fiscal_address = models.TextField('domicilio fiscal', blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=50, blank=True)
    is_special_taxpayer = models.BooleanField('contribuyente especial', default=False)
    vat_withholding_percent = models.PositiveSmallIntegerField(
        'retencion de IVA que aplica', choices=VAT_WITHHOLDING_CHOICES, default=0,
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('tenant', 'rif')
        ordering = ['name']

    def __str__(self):
        return f'{self.name} ({self.rif})'


class DocumentSequence(models.Model):
    """Correlativos de la empresa. `doc_type='control'` es el numero de control,
    unico y compartido por facturas y notas."""

    tenant = models.ForeignKey('tenants.Tenant', on_delete=models.CASCADE, related_name='document_sequences')
    doc_type = models.CharField(max_length=20)
    last_number = models.PositiveBigIntegerField(default=0)

    class Meta:
        unique_together = ('tenant', 'doc_type')


class Invoice(models.Model):
    DOC_TYPES = [
        ('invoice', 'Factura'),
        ('debit_note', 'Nota de debito'),
        ('credit_note', 'Nota de credito'),
    ]
    STATUS_CHOICES = [
        ('draft', 'Borrador'),
        ('issued', 'Emitida'),
        ('partial', 'Pago parcial'),
        ('paid', 'Pagada'),
        ('void', 'Anulada'),
    ]
    tenant = models.ForeignKey('tenants.Tenant', on_delete=models.CASCADE, related_name='sales_invoices')
    doc_type = models.CharField(max_length=20, choices=DOC_TYPES, default='invoice')
    number = models.CharField('numero', max_length=20, blank=True)
    control_number = models.CharField('numero de control', max_length=20, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name='invoices')
    related_invoice = models.ForeignKey(
        'self', null=True, blank=True, on_delete=models.PROTECT, related_name='adjustment_notes',
        help_text='Factura que afecta una nota de credito o debito.',
    )
    issue_date = models.DateField()
    due_date = models.DateField(null=True, blank=True)
    currency = models.CharField(max_length=10, default='VES')
    exchange_rate = models.DecimalField(
        'tasa BCV', max_digits=18, decimal_places=6, default=1,
        help_text='Bolivares por unidad de la moneda de la factura en la fecha de emision.',
    )

    # Datos del cliente congelados al emitir
    customer_rif = models.CharField(max_length=12, blank=True)
    customer_name = models.CharField(max_length=255, blank=True)
    customer_address = models.TextField(blank=True)

    # Totales en la moneda de la factura
    exempt_amount = models.DecimalField('exento', **MONEY)
    base_general = models.DecimalField(**MONEY)
    tax_general = models.DecimalField(**MONEY)
    base_reduced = models.DecimalField(**MONEY)
    tax_reduced = models.DecimalField(**MONEY)
    base_luxury = models.DecimalField(**MONEY)
    tax_luxury = models.DecimalField(**MONEY)
    subtotal = models.DecimalField(**MONEY)
    tax_total = models.DecimalField(**MONEY)
    total = models.DecimalField(**MONEY)
    vat_rates = models.JSONField(default=dict, blank=True, help_text='Alicuotas aplicadas al emitir.')

    # Cobro
    amount_paid = models.DecimalField(**MONEY)
    vat_withheld = models.DecimalField('IVA retenido por el cliente', **MONEY)
    credited = models.DecimalField('acreditado por notas de credito', **MONEY)
    balance_due = models.DecimalField(**MONEY)

    notes = models.TextField(blank=True)
    void_reason = models.TextField(blank=True)
    issued_at = models.DateTimeField(null=True, blank=True)
    voided_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+',
    )
    issued_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+',
    )
    journal_entry = models.ForeignKey(
        'finance_accounts.JournalEntry', null=True, blank=True, on_delete=models.SET_NULL, related_name='+',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-issue_date', '-id']
        constraints = [
            models.UniqueConstraint(
                fields=['tenant', 'doc_type', 'number'], condition=~models.Q(number=''),
                name='sales_unique_document_number',
            ),
            models.UniqueConstraint(
                fields=['tenant', 'control_number'], condition=~models.Q(control_number=''),
                name='sales_unique_control_number',
            ),
        ]

    def __str__(self):
        return f'{self.get_doc_type_display()} {self.number or "(borrador)"}'

    @property
    def is_editable(self):
        return self.status == 'draft'

    @property
    def sign(self):
        """+1 para facturas y notas de debito, -1 para notas de credito (libro de ventas)."""
        return -1 if self.doc_type == 'credit_note' else 1


class InvoiceLine(models.Model):
    TAX_CATEGORIES = [
        ('general', 'Alicuota general'),
        ('reduced', 'Alicuota reducida'),
        ('luxury', 'General + adicional (suntuarios)'),
        ('exempt', 'Exento / exonerado / no sujeto'),
    ]
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='lines')
    description = models.CharField(max_length=500)
    quantity = models.DecimalField(max_digits=14, decimal_places=3, default=1,
                                   validators=[MinValueValidator(Decimal('0'))])
    unit_price = models.DecimalField(max_digits=18, decimal_places=2, validators=[MinValueValidator(Decimal('0'))])
    discount_percent = models.DecimalField(
        max_digits=5, decimal_places=2, default=0,
        validators=[MinValueValidator(Decimal('0')), MaxValueValidator(Decimal('100'))],
    )
    tax_category = models.CharField(max_length=10, choices=TAX_CATEGORIES, default='general')
    line_base = models.DecimalField(**MONEY)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return self.description


class InvoicePayment(models.Model):
    METHOD_CHOICES = [
        ('transfer', 'Transferencia en Bs'),
        ('mobile_payment', 'Pago movil'),
        ('pos', 'Punto de venta'),
        ('cash_ves', 'Efectivo en Bs'),
        ('cash_foreign', 'Efectivo en divisas'),
        ('foreign_transfer', 'Transferencia en divisas'),
        ('zelle', 'Zelle'),
        ('other', 'Otro'),
    ]
    tenant = models.ForeignKey('tenants.Tenant', on_delete=models.CASCADE, related_name='sales_payments')
    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name='payments')
    payment_date = models.DateField()
    method = models.CharField(max_length=20, choices=METHOD_CHOICES, default='transfer')
    reference = models.CharField(max_length=100, blank=True)
    currency = models.CharField(max_length=10, default='VES')
    amount = models.DecimalField('monto abonado a la factura', max_digits=18, decimal_places=2,
                                 validators=[MinValueValidator(Decimal('0.01'))])
    exchange_rate = models.DecimalField('tasa BCV del pago', max_digits=18, decimal_places=6, default=1)
    amount_ves = models.DecimalField(**MONEY)
    applied_amount = models.DecimalField('abonado en la moneda de la factura', **MONEY)
    igtf_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    igtf_amount = models.DecimalField('IGTF percibido (moneda del pago)', **MONEY)
    igtf_amount_ves = models.DecimalField(**MONEY)
    fx_difference_ves = models.DecimalField('diferencial cambiario (Bs)', **MONEY)
    journal_entry = models.ForeignKey(
        'finance_accounts.JournalEntry', null=True, blank=True, on_delete=models.SET_NULL, related_name='+',
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-payment_date', '-id']

    def __str__(self):
        return f'Pago {self.amount} {self.currency} a {self.invoice}'


class VatWithholding(models.Model):
    """Comprobante de retencion de IVA entregado por un cliente contribuyente especial."""

    tenant = models.ForeignKey('tenants.Tenant', on_delete=models.CASCADE, related_name='vat_withholdings')
    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name='vat_withholdings')
    voucher_number = models.CharField(
        'numero de comprobante', max_length=14,
        validators=[RegexValidator(r'^\d{14}$', 'El comprobante tiene 14 digitos (AAAAMM + 8 correlativos).')],
    )
    voucher_date = models.DateField()
    percent = models.PositiveSmallIntegerField(choices=[(75, '75%'), (100, '100%')])
    amount = models.DecimalField('monto retenido (moneda de la factura)', **MONEY)
    amount_ves = models.DecimalField(**MONEY)
    journal_entry = models.ForeignKey(
        'finance_accounts.JournalEntry', null=True, blank=True, on_delete=models.SET_NULL, related_name='+',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('tenant', 'invoice', 'voucher_number')

    def __str__(self):
        return f'Retencion IVA {self.voucher_number}'
