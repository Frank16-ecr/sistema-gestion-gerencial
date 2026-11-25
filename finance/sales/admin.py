from django.contrib import admin

from .models import Customer, Invoice, InvoiceLine, InvoicePayment, TaxpayerProfile, VatWithholding


@admin.register(TaxpayerProfile)
class TaxpayerProfileAdmin(admin.ModelAdmin):
    list_display = ('legal_name', 'rif', 'tenant', 'is_special_taxpayer', 'igtf_collection_agent')


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ('name', 'rif', 'tenant', 'is_special_taxpayer', 'vat_withholding_percent', 'is_active')
    list_filter = ('tenant', 'is_special_taxpayer', 'is_active')
    search_fields = ('name', 'rif')


class InvoiceLineInline(admin.TabularInline):
    model = InvoiceLine
    extra = 0
    readonly_fields = ('line_base',)


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'control_number', 'tenant', 'customer_name', 'issue_date', 'currency', 'total',
                    'balance_due', 'status')
    list_filter = ('tenant', 'doc_type', 'status', 'currency')
    search_fields = ('number', 'control_number', 'customer_name', 'customer_rif')
    inlines = [InvoiceLineInline]

    def has_delete_permission(self, request, obj=None):
        return obj is None or obj.is_editable


@admin.register(InvoicePayment)
class InvoicePaymentAdmin(admin.ModelAdmin):
    list_display = ('invoice', 'payment_date', 'currency', 'amount', 'igtf_amount', 'amount_ves')
    list_filter = ('tenant', 'currency', 'method')


@admin.register(VatWithholding)
class VatWithholdingAdmin(admin.ModelAdmin):
    list_display = ('voucher_number', 'invoice', 'voucher_date', 'percent', 'amount_ves')
