from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class EmployeePayrollProfile(models.Model):
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, related_name='employee_profiles')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='payroll_profile')
    employee_number = models.CharField(max_length=50)
    tin_number = models.CharField(max_length=50, blank=True)
    nssf_number = models.CharField(max_length=50, blank=True)
    bank_name = models.CharField(max_length=100, blank=True)
    bank_account_number = models.CharField(max_length=50, blank=True)
    gross_salary = models.DecimalField(max_digits=18, decimal_places=2)
    income_tax_rate = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(Decimal('0')), MaxValueValidator(Decimal('100'))],
        help_text="Porcentaje de retencion del impuesto sobre la renta del trabajador "
                  "(en Venezuela, el del formulario AR-I). Se usa con income_tax.method='employee_rate'.",
    )
    is_active = models.BooleanField(default=True)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("tenant", "employee_number")

    def __str__(self):
        return f"{self.employee_number} - {self.user}"


class EmployeeAllowance(models.Model):
    ALLOWANCE_TYPES = [
        ("transport", "Transport"),
        ("housing", "Housing"),
        ("medical", "Medical"),
        ("lunch", "Lunch"),
        ("other", "Other"),
    ]
    employee = models.ForeignKey(EmployeePayrollProfile, on_delete=models.CASCADE, related_name='allowances')
    allowance_type = models.CharField(max_length=30, choices=ALLOWANCE_TYPES)
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    is_taxable = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.employee} - {self.allowance_type}: {self.amount}"


class PayrollRun(models.Model):
    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("approved", "Approved"),
        ("paid", "Paid"),
    ]
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, related_name='payroll_runs')
    PERIOD_CHOICES = [
        ("monthly", "Mensual"),
        ("q1", "1ra quincena"),
        ("q2", "2da quincena"),
    ]
    month = models.PositiveIntegerField()
    year = models.PositiveIntegerField()
    period = models.CharField(max_length=10, choices=PERIOD_CHOICES, default="monthly")
    period_start = models.DateField(null=True, blank=True)
    period_end = models.DateField(null=True, blank=True)
    mondays = models.PositiveSmallIntegerField(
        default=0, help_text="Lunes del periodo (base de la cotizacion semanal IVSS/RPE).",
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="draft")
    total_gross = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    total_paye = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    total_nssf_employee = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    total_nssf_employer = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    total_net = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    contributions_summary = models.JSONField(
        default=dict, blank=True, help_text="Totales de trabajador y patrono por aporte (ivss, faov...).",
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='approved_payrolls',
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='created_payrolls',
    )
    journal_entry = models.ForeignKey(
        'finance_accounts.JournalEntry', null=True, blank=True, on_delete=models.SET_NULL, related_name='+',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("tenant", "month", "year", "period")

    def __str__(self):
        suffix = '' if self.period == 'monthly' else f" {self.get_period_display()}"
        return f"{self.year}-{self.month:02d}{suffix} ({self.tenant})"


class PayrollLine(models.Model):
    payroll_run = models.ForeignKey(PayrollRun, on_delete=models.CASCADE, related_name='lines')
    employee = models.ForeignKey(EmployeePayrollProfile, on_delete=models.CASCADE, related_name='payroll_lines')
    gross_salary = models.DecimalField(max_digits=18, decimal_places=2)
    total_allowances = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    taxable_income = models.DecimalField(max_digits=18, decimal_places=2)
    paye = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    nssf_employee = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    nssf_employer = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    net_pay = models.DecimalField(max_digits=18, decimal_places=2)
    contributions = models.JSONField(
        default=dict, blank=True, help_text="Detalle por aporte: base, trabajador, patrono.",
    )
    notes = models.TextField(blank=True)

    def __str__(self):
        return f"PayrollLine for {self.employee} in {self.payroll_run}"
