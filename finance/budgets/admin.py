from django.contrib import admin

from .models import Budget, BudgetLine


class BudgetLineInline(admin.TabularInline):
    model = BudgetLine
    extra = 1


@admin.register(Budget)
class BudgetAdmin(admin.ModelAdmin):
    list_display = ('name', 'fiscal_year', 'tenant', 'currency', 'status', 'period_start', 'period_end')
    list_filter = ('status', 'fiscal_year', 'currency', 'tenant')
    search_fields = ('name', 'notes')
    inlines = [BudgetLineInline]


@admin.register(BudgetLine)
class BudgetLineAdmin(admin.ModelAdmin):
    list_display = ('budget', 'category', 'planned_amount')
    list_filter = ('category',)
