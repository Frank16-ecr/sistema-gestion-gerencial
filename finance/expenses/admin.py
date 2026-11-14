from django.contrib import admin
from .models import Expense, ReimbursementRequest, ReimbursementBatch


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ('description', 'category', 'amount', 'currency', 'status', 'expense_date', 'tenant', 'submitted_by')
    search_fields = ('description', 'notes')
    list_filter = ('category', 'status', 'currency', 'tenant')
    date_hierarchy = 'expense_date'


@admin.register(ReimbursementBatch)
class ReimbursementBatchAdmin(admin.ModelAdmin):
    list_display = ('batch_number', 'tenant', 'week_start', 'week_end', 'total_amount', 'status', 'created_at')
    search_fields = ('batch_number',)
    list_filter = ('status', 'tenant')


@admin.register(ReimbursementRequest)
class ReimbursementRequestAdmin(admin.ModelAdmin):
    list_display = ('description', 'tenant', 'amount', 'currency', 'status', 'submitted_by', 'created_at')
    search_fields = ('description', 'notes')
    list_filter = ('status', 'currency', 'tenant')
