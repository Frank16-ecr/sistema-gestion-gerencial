from django.contrib import admin
from .models import EmployeePayrollProfile, EmployeeAllowance, PayrollRun, PayrollLine


@admin.register(EmployeePayrollProfile)
class EmployeePayrollProfileAdmin(admin.ModelAdmin):
    list_display = ('employee_number', 'user', 'tenant', 'gross_salary', 'is_active', 'start_date')
    search_fields = ('employee_number', 'user__username', 'tin_number', 'nssf_number')
    list_filter = ('is_active', 'tenant')


@admin.register(EmployeeAllowance)
class EmployeeAllowanceAdmin(admin.ModelAdmin):
    list_display = ('employee', 'allowance_type', 'amount', 'is_taxable', 'is_active')
    list_filter = ('allowance_type', 'is_taxable', 'is_active')


class PayrollLineInline(admin.TabularInline):
    model = PayrollLine
    extra = 0


@admin.register(PayrollRun)
class PayrollRunAdmin(admin.ModelAdmin):
    list_display = ('tenant', 'year', 'month', 'status', 'total_gross', 'total_net', 'created_at')
    list_filter = ('status', 'tenant', 'year')
    inlines = [PayrollLineInline]


@admin.register(PayrollLine)
class PayrollLineAdmin(admin.ModelAdmin):
    list_display = ('payroll_run', 'employee', 'gross_salary', 'paye', 'nssf_employee', 'net_pay')
    search_fields = ('employee__employee_number',)
