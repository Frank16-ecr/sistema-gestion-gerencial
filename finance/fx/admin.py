from django.contrib import admin

from .models import ExchangeRate


@admin.register(ExchangeRate)
class ExchangeRateAdmin(admin.ModelAdmin):
    list_display = ('from_currency', 'to_currency', 'rate', 'rate_date', 'source', 'tenant', 'created_at')
    search_fields = ('from_currency', 'to_currency')
    list_filter = ('source', 'from_currency', 'to_currency', 'tenant')
    date_hierarchy = 'rate_date'
