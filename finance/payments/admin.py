from django.contrib import admin
from .models import FeeNotePayment, WHTCredit


@admin.register(FeeNotePayment)
class FeeNotePaymentAdmin(admin.ModelAdmin):
    list_display = ('fee_note', 'tenant', 'payment_currency', 'amount_received_foreign', 'payment_date', 'payment_method', 'created_at')
    search_fields = ('fee_note__fee_note_number', 'bank_reference', 'efris_receipt_ref')
    list_filter = ('payment_currency', 'payment_method', 'wht_deducted', 'tenant')
    date_hierarchy = 'payment_date'


@admin.register(WHTCredit)
class WHTCreditAdmin(admin.ModelAdmin):
    list_display = ('cert_number', 'tenant', 'amount', 'period_year', 'period_month', 'is_utilised', 'created_at')
    search_fields = ('cert_number',)
    list_filter = ('is_utilised', 'tenant', 'period_year')
