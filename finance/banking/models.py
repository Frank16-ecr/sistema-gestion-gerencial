from django.db import models
from django.conf import settings


class BankAccount(models.Model):
    ACCOUNT_TYPES = [
        ("current", "Current"),
        ("savings", "Savings"),
        ("petty_cash", "Petty Cash"),
    ]
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, related_name='bank_accounts')
    account_name = models.CharField(max_length=255)
    bank_name = models.CharField(max_length=255)
    account_number = models.CharField(max_length=50)
    currency = models.CharField(max_length=10, default="UGX")
    account_type = models.CharField(max_length=20, choices=ACCOUNT_TYPES, default="current")
    opening_balance = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    current_balance = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.account_name} ({self.bank_name})"


class BankReconciliation(models.Model):
    STATUS_CHOICES = [
        ("open", "Open"),
        ("locked", "Locked"),
    ]
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, related_name='bank_reconciliations')
    bank_account = models.ForeignKey(BankAccount, on_delete=models.CASCADE, related_name='reconciliations')
    period_month = models.PositiveIntegerField()
    period_year = models.PositiveIntegerField()
    opening_balance = models.DecimalField(max_digits=18, decimal_places=2)
    closing_balance_per_bank = models.DecimalField(max_digits=18, decimal_places=2)
    closing_balance_per_system = models.DecimalField(max_digits=18, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="open")
    locked_at = models.DateTimeField(null=True, blank=True)
    locked_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("bank_account", "period_month", "period_year")

    def __str__(self):
        return f"Reconciliation {self.bank_account} {self.period_year}/{self.period_month:02d}"


class PettyCashTransaction(models.Model):
    TRANSACTION_TYPES = [
        ("withdrawal", "Withdrawal"),
        ("top_up", "Top Up"),
    ]
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, related_name='petty_cash_transactions')
    bank_account = models.ForeignKey(BankAccount, on_delete=models.CASCADE, related_name='petty_cash_transactions')
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES)
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    description = models.CharField(max_length=255)
    transaction_date = models.DateField()
    reference = models.CharField(max_length=100, blank=True)
    claim_id = models.UUIDField(null=True, blank=True)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.transaction_type} - {self.amount} on {self.transaction_date}"


class Cheque(models.Model):
    CHEQUE_TYPES = [("receipt", "Receipt"), ("issued", "Issued")]
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("cleared", "Cleared"),
        ("bounced", "Bounced"),
        ("cancelled", "Cancelled"),
    ]
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, related_name='cheques')
    bank_account = models.ForeignKey(BankAccount, on_delete=models.CASCADE, related_name='cheques')
    cheque_type = models.CharField(max_length=10, choices=CHEQUE_TYPES)
    cheque_number = models.CharField(max_length=50)
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    payee_payer = models.CharField(max_length=255)
    issue_date = models.DateField()
    cleared_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    fee_note = models.ForeignKey("finance_invoicing.FeeNote", null=True, blank=True, on_delete=models.SET_NULL, related_name='cheques')
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Cheque {self.cheque_number} - {self.payee_payer}"
