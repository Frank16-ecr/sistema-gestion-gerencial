from decimal import Decimal

from django.db import transaction

from rest_framework import serializers

from . import services
from .models import Customer, Invoice, InvoiceLine, InvoicePayment, TaxpayerProfile, VatWithholding


class TaxpayerProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = TaxpayerProfile
        fields = '__all__'


class CustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = '__all__'
        read_only_fields = ('created_at',)

    def validate_rif(self, value):
        return value.upper()


class InvoiceLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = InvoiceLine
        exclude = ('invoice',)
        read_only_fields = ('line_base',)


class InvoicePaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = InvoicePayment
        fields = '__all__'
        read_only_fields = [f.name for f in InvoicePayment._meta.fields]


class VatWithholdingSerializer(serializers.ModelSerializer):
    class Meta:
        model = VatWithholding
        fields = '__all__'
        read_only_fields = [f.name for f in VatWithholding._meta.fields]


EDITABLE_INVOICE_FIELDS = (
    'tenant', 'doc_type', 'customer', 'related_invoice', 'issue_date', 'due_date', 'currency', 'notes',
)


class InvoiceSerializer(serializers.ModelSerializer):
    lines = InvoiceLineSerializer(many=True)
    payments = InvoicePaymentSerializer(many=True, read_only=True)
    vat_withholdings = VatWithholdingSerializer(many=True, read_only=True)
    total_ves = serializers.SerializerMethodField()
    tax_total_ves = serializers.SerializerMethodField()

    class Meta:
        model = Invoice
        fields = '__all__'
        read_only_fields = [
            f.name for f in Invoice._meta.fields if f.name not in EDITABLE_INVOICE_FIELDS
        ]

    def get_total_ves(self, obj):
        return services.to_ves(obj.total, obj.exchange_rate) if obj.status != 'draft' else None

    def get_tax_total_ves(self, obj):
        return services.to_ves(obj.tax_total, obj.exchange_rate) if obj.status != 'draft' else None

    def validate(self, attrs):
        if self.instance is not None and not self.instance.is_editable:
            raise serializers.ValidationError(
                'Los documentos emitidos no se modifican: anulalos o emite una nota de credito o debito.'
            )
        tenant = attrs.get('tenant', getattr(self.instance, 'tenant', None))
        customer = attrs.get('customer', getattr(self.instance, 'customer', None))
        related = attrs.get('related_invoice', getattr(self.instance, 'related_invoice', None))
        if customer and tenant and customer.tenant_id != tenant.pk:
            raise serializers.ValidationError({'customer': 'El cliente pertenece a otra empresa.'})
        if related and tenant and related.tenant_id != tenant.pk:
            raise serializers.ValidationError({'related_invoice': 'La factura afectada pertenece a otra empresa.'})
        if 'currency' in attrs:
            attrs['currency'] = attrs['currency'].upper()
        lines = attrs.get('lines')
        if lines is not None and not lines:
            raise serializers.ValidationError({'lines': 'Agrega al menos una linea.'})
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        lines = validated_data.pop('lines')
        invoice = Invoice.objects.create(**validated_data)
        for line in lines:
            InvoiceLine.objects.create(invoice=invoice, **line)
        return services.recalculate(invoice)

    @transaction.atomic
    def update(self, instance, validated_data):
        lines = validated_data.pop('lines', None)
        for key, value in validated_data.items():
            setattr(instance, key, value)
        instance.save()
        if lines is not None:
            instance.lines.all().delete()
            for line in lines:
                InvoiceLine.objects.create(invoice=instance, **line)
        return services.recalculate(instance)


class VoidSerializer(serializers.Serializer):
    reason = serializers.CharField()


class PaymentInputSerializer(serializers.Serializer):
    payment_date = serializers.DateField()
    amount = serializers.DecimalField(max_digits=18, decimal_places=2, min_value=Decimal('0.01'))
    currency = serializers.CharField(max_length=10, default='VES')
    method = serializers.ChoiceField(choices=InvoicePayment.METHOD_CHOICES, default='transfer')
    reference = serializers.CharField(max_length=100, required=False, allow_blank=True, default='')


class WithholdingInputSerializer(serializers.Serializer):
    voucher_number = serializers.RegexField(r'^\d{14}$')
    voucher_date = serializers.DateField()
    percent = serializers.ChoiceField(choices=[75, 100], required=False)
