from django.conf import settings
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
    month = models.PositiveIntegerField()
    year = models.PositiveIntegerField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="draft")
    total_gross = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    total_paye = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    total_nssf_employee = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    total_nssf_employer = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    total_net = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='approved_payrolls',
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='created_payrolls',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("tenant", "month", "year")

    def __str__(self):
        return f"Payroll {self.year}-{self.month:02d} ({self.tenant})"


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
    notes = models.TextField(blank=True)

    def __str__(self):
        return f"PayrollLine for {self.employee} in {self.payroll_run}"
