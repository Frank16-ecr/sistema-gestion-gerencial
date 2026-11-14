from django.contrib import admin

from .models import Investment, InvestmentMovement


class InvestmentMovementInline(admin.TabularInline):
    model = InvestmentMovement
    extra = 0


@admin.register(Investment)
class InvestmentAdmin(admin.ModelAdmin):
    list_display = ('name', 'asset_type', 'tenant', 'currency', 'initial_amount', 'status', 'start_date', 'maturity_date')
    list_filter = ('asset_type', 'status', 'currency', 'tenant')
    search_fields = ('name', 'institution', 'notes')
    inlines = [InvestmentMovementInline]


@admin.register(InvestmentMovement)
class InvestmentMovementAdmin(admin.ModelAdmin):
    list_display = ('investment', 'movement_type', 'amount', 'movement_date')
    list_filter = ('movement_type',)
