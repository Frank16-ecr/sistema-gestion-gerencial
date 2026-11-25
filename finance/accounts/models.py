from django.conf import settings
from django.db import models


class Account(models.Model):
    CATEGORY_CHOICES = [
        ("asset", "Asset"),
        ("liability", "Liability"),
        ("equity", "Equity"),
        ("income", "Income"),
        ("expense", "Expense"),
    ]
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, related_name='accounts')
    code = models.CharField(max_length=20)
    name = models.CharField(max_length=255)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    parent = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL, related_name='children')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("tenant", "code")

    def __str__(self):
        return f"{self.code} - {self.name}"


class JournalEntry(models.Model):
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, related_name='journal_entries')
    entry_date = models.DateField()
    reference = models.CharField(max_length=100, blank=True)
    description = models.TextField(blank=True)
    created_by_system = models.BooleanField(default=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    is_void = models.BooleanField(default=False)
    void_reason = models.TextField(blank=True)
    voided_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"JE-{self.pk} ({self.entry_date})"

    class Meta:
        verbose_name_plural = "Journal Entries"


class JournalLine(models.Model):
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, related_name='journal_lines')
    journal_entry = models.ForeignKey(JournalEntry, on_delete=models.CASCADE, related_name="lines")
    account = models.ForeignKey(Account, on_delete=models.PROTECT)
    debit_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    credit_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    foreign_currency = models.CharField(max_length=10, blank=True, null=True)
    foreign_amount = models.DecimalField(max_digits=18, decimal_places=2, blank=True, null=True)
    exchange_rate = models.DecimalField(max_digits=18, decimal_places=6, blank=True, null=True)
    claim_id = models.UUIDField(blank=True, null=True)
    description = models.TextField(blank=True)

    def __str__(self):
        return f"Line for JE-{self.journal_entry_id}: {self.account}"
