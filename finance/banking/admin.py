from django.contrib import admin
from .models import BankAccount, BankReconciliation, PettyCashTransaction, Cheque


@admin.register(BankAccount)
class BankAccountAdmin(admin.ModelAdmin):
    list_display = ('account_name', 'bank_name', 'account_number', 'currency', 'account_type', 'current_balance', 'is_active')
    search_fields = ('account_name', 'bank_name', 'account_number')
    list_filter = ('account_type', 'currency', 'is_active', 'tenant')


@admin.register(BankReconciliation)
class BankReconciliationAdmin(admin.ModelAdmin):
    list_display = ('bank_account', 'tenant', 'period_year', 'period_month', 'status', 'created_at')
    list_filter = ('status', 'tenant', 'period_year')


@admin.register(PettyCashTransaction)
class PettyCashTransactionAdmin(admin.ModelAdmin):
    list_display = ('bank_account', 'transaction_type', 'amount', 'description', 'transaction_date', 'tenant')
    search_fields = ('description', 'reference')
    list_filter = ('transaction_type', 'tenant')
    date_hierarchy = 'transaction_date'


@admin.register(Cheque)
class ChequeAdmin(admin.ModelAdmin):
    list_display = ('cheque_number', 'cheque_type', 'bank_account', 'amount', 'payee_payer', 'issue_date', 'status')
    search_fields = ('cheque_number', 'payee_payer')
    list_filter = ('cheque_type', 'status', 'tenant')
    date_hierarchy = 'issue_date'
