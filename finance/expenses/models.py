from django.conf import settings
from django.db import models

from tenants.config import default_currency


class Expense(models.Model):
    CATEGORY_CHOICES = [
        ("rent", "Alquiler"),
        ("internet", "Internet"),
        ("fuel", "Combustible"),
        ("audit_fees", "Honorarios de auditoría"),
        ("utilities", "Servicios básicos"),
        ("office_supplies", "Material de oficina"),
        ("travel", "Viajes"),
        ("other", "Otros"),
    ]
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("approved", "Approved"),
        ("paid", "Paid"),
        ("rejected", "Rejected"),
    ]
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, related_name='expenses')
    description = models.CharField(max_length=255)
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES)
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    currency = models.CharField(max_length=10, default=default_currency)
    expense_date = models.DateField()
    claim_id = models.UUIDField(null=True, blank=True)
    receipt_file = models.FileField(upload_to="finance/expenses/", null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='submitted_expenses',
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_expenses',
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.category} - {self.description} ({self.amount} {self.currency})"


class ReimbursementBatch(models.Model):
    STATUS_CHOICES = [
        ("open", "Open"),
        ("processing", "Processing"),
        ("paid", "Paid"),
    ]
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, related_name='reimbursement_batches')
    batch_number = models.CharField(max_length=50, unique=True)
    week_start = models.DateField()
    week_end = models.DateField()
    total_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="open")
    paid_at = models.DateTimeField(null=True, blank=True)
    paid_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.batch_number


class ReimbursementRequest(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("approved", "Approved"),
        ("batched", "Batched"),
        ("paid", "Paid"),
        ("rejected", "Rejected"),
    ]
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, related_name='reimbursement_requests')
    claim_id = models.UUIDField()
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='reimbursement_requests',
    )
    description = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    currency = models.CharField(max_length=10, default=default_currency)
    receipt_file = models.FileField(upload_to="finance/reimbursements/", null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='approved_reimbursements',
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    batch = models.ForeignKey(
        ReimbursementBatch, null=True, blank=True, on_delete=models.SET_NULL, related_name='items',
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Reimbursement: {self.description} ({self.amount} {self.currency})"
