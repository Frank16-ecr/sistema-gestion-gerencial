import csv
from datetime import date

from django.http import HttpResponse

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from finance.accounts.services import AccountingConfigError
from finance.reports.views import TenantReportView
from finance.security.permissions import ADMIN_ROLES, TenantScopedMixin

from . import services
from .models import Customer, Invoice, InvoicePayment, TaxpayerProfile, VatWithholding
from .serializers import (
    CustomerSerializer, InvoicePaymentSerializer, InvoiceSerializer, PaymentInputSerializer, TaxpayerProfileSerializer,
    VatWithholdingSerializer, VoidSerializer, WithholdingInputSerializer,
)


def _service_call(func, *args, **kwargs):
    try:
        return func(*args, **kwargs)
    except (services.InvoiceError, AccountingConfigError) as exc:
        raise ValidationError({'detail': str(exc)})


class TaxpayerProfileViewSet(TenantScopedMixin, viewsets.ModelViewSet):
    write_roles = ADMIN_ROLES
    queryset = TaxpayerProfile.objects.all()
    serializer_class = TaxpayerProfileSerializer
    filterset_fields = ('tenant',)


class CustomerViewSet(TenantScopedMixin, viewsets.ModelViewSet):
    queryset = Customer.objects.all()
    serializer_class = CustomerSerializer
    filterset_fields = ('tenant', 'is_special_taxpayer', 'is_active')
    search_fields = ('rif', 'name')

    def perform_destroy(self, instance):
        if instance.invoices.exists():
            raise ValidationError({'detail': 'El cliente tiene documentos: desactivalo en lugar de borrarlo.'})
        instance.delete()


class InvoiceViewSet(TenantScopedMixin, viewsets.ModelViewSet):
    """Facturas y notas de credito/debito.

    Se crean en borrador (editables) y se emiten con `issue`. Los documentos
    emitidos no se editan ni se borran: se anulan (`void`) o se corrigen con notas.
    """

    queryset = Invoice.objects.select_related('customer', 'related_invoice').prefetch_related(
        'lines', 'payments', 'vat_withholdings')
    serializer_class = InvoiceSerializer
    filterset_fields = ('tenant', 'doc_type', 'status', 'customer', 'currency', 'issue_date')
    search_fields = ('number', 'control_number', 'customer_name', 'customer_rif')

    def perform_destroy(self, instance):
        if not instance.is_editable:
            raise ValidationError({'detail': 'Los documentos emitidos no se borran: anulalos.'})
        instance.delete()

    def _respond(self, invoice, code=status.HTTP_200_OK):
        invoice = self.get_queryset().get(pk=invoice.pk)
        return Response(InvoiceSerializer(invoice).data, status=code)

    @action(detail=True, methods=['post'])
    def issue(self, request, pk=None):
        invoice = _service_call(services.issue_invoice, self.get_object(), user=request.user)
        return self._respond(invoice)

    @action(detail=True, methods=['post'])
    def void(self, request, pk=None):
        data = VoidSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        invoice = _service_call(services.void_invoice, self.get_object(), data.validated_data['reason'],
                                user=request.user)
        return self._respond(invoice)

    @action(detail=True, methods=['post'])
    def pay(self, request, pk=None):
        data = PaymentInputSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        d = data.validated_data
        payment = _service_call(
            services.register_payment, self.get_object(), d['payment_date'], d['amount'], d['currency'].upper(),
            method=d['method'], reference=d['reference'], user=request.user,
        )
        return Response(InvoicePaymentSerializer(payment).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def withholding(self, request, pk=None):
        data = WithholdingInputSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        d = data.validated_data
        withholding = _service_call(
            services.register_vat_withholding, self.get_object(), d['voucher_number'], d['voucher_date'],
            percent=d.get('percent'), user=request.user,
        )
        return Response(VatWithholdingSerializer(withholding).data, status=status.HTTP_201_CREATED)


class InvoicePaymentViewSet(TenantScopedMixin, viewsets.ReadOnlyModelViewSet):
    queryset = InvoicePayment.objects.select_related('invoice')
    serializer_class = InvoicePaymentSerializer
    filterset_fields = ('tenant', 'invoice', 'currency', 'method', 'payment_date')


class VatWithholdingViewSet(TenantScopedMixin, viewsets.ReadOnlyModelViewSet):
    queryset = VatWithholding.objects.select_related('invoice')
    serializer_class = VatWithholdingSerializer
    filterset_fields = ('tenant', 'invoice')


SALES_BOOK_COLUMNS = [
    ('line', 'N°'), ('date', 'Fecha'), ('doc_type', 'Tipo de documento'), ('number', 'N° documento'),
    ('control_number', 'N° de control'), ('customer_rif', 'RIF'), ('customer_name', 'Nombre o razon social'),
    ('affected_invoice', 'Factura afectada'), ('status', 'Estado'), ('currency', 'Moneda'),
    ('exchange_rate', 'Tasa BCV'), ('total', 'Total ventas con IVA (Bs)'), ('exempt', 'Ventas exentas (Bs)'),
    ('base_general', 'Base alicuota general'), ('tax_general', 'IVA alicuota general'),
    ('base_reduced', 'Base alicuota reducida'), ('tax_reduced', 'IVA alicuota reducida'),
    ('base_luxury', 'Base alicuota general + adicional'), ('tax_luxury', 'IVA alicuota general + adicional'),
    ('vat_withheld', 'IVA retenido por el comprador'), ('withholding_voucher', 'N° comprobante de retencion'),
]


class SalesBookView(TenantReportView):
    """Libro de ventas mensual en bolivares. `?export=csv` lo descarga para Excel."""

    def get(self, request):
        tenant = self.get_tenant(request)
        try:
            year = int(request.query_params.get('year', date.today().year))
            month = int(request.query_params.get('month', date.today().month))
            if not 1 <= month <= 12:
                raise ValueError
        except ValueError:
            raise ValidationError({'detail': 'year y month deben ser numeros validos (month entre 1 y 12).'})
        book = services.sales_book(tenant, year, month)
        if request.query_params.get('export') != 'csv':
            return Response(book)

        response = HttpResponse(content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = f'attachment; filename="libro_ventas_{tenant.slug}_{year}_{month:02d}.csv"'
        response.write('﻿')  # BOM para que Excel reconozca UTF-8
        writer = csv.writer(response, delimiter=';')
        writer.writerow([label for _, label in SALES_BOOK_COLUMNS])
        for row in book['rows']:
            writer.writerow([_csv_value(row[key]) for key, _ in SALES_BOOK_COLUMNS])
        totals = book['totals']
        writer.writerow(['', '', '', '', '', '', 'TOTALES', '', '', '', ''] + [
            _csv_value(totals[key]) for key, _ in SALES_BOOK_COLUMNS[11:20]
        ] + [''])
        return response


def _csv_value(value):
    if isinstance(value, date):
        return value.strftime('%d/%m/%Y')
    if hasattr(value, 'quantize'):
        return f'{value:.2f}'.replace('.', ',')
    return value
