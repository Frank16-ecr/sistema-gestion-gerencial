from django.contrib import admin

from .models import StatutoryObligation


@admin.register(StatutoryObligation)
class StatutoryObligationAdmin(admin.ModelAdmin):
    list_display = ('obligation_type', 'tenant', 'period_year', 'period_month', 'amount_due', 'due_date', 'status')
    search_fields = ('payment_reference', 'notes')
    list_filter = ('obligation_type', 'status', 'tenant', 'period_year')
    date_hierarchy = 'due_date'
