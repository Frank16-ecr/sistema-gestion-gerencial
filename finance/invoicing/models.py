from django.conf import settings
from django.db import models

from tenants.config import default_currency


class FeeNote(models.Model):
    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("submitted", "Submitted to EFRIS"),
        ("stamped", "EFRIS Stamped"),
        ("sent", "Sent to Insurer"),
        ("partial", "Partially Paid"),
        ("paid", "Paid"),
        ("overdue_1", "Overdue 30"),
        ("overdue_2", "Overdue 60"),
        ("overdue_3", "Overdue 90+"),
        ("void", "Void"),
    ]
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, related_name='fee_notes')
    claim_id = models.UUIDField()
    fee_note_number = models.CharField(max_length=50, unique=True)
    insurer_id = models.UUIDField()
    insurer_name = models.CharField(max_length=255, blank=True)
    insurer_email = models.EmailField(blank=True)
    invoice_currency = models.CharField(max_length=10, default=default_currency)
    invoice_amount = models.DecimalField(max_digits=18, decimal_places=2)
    vat_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=18, decimal_places=2)
    exchange_rate_at_issue = models.DecimalField(max_digits=18, decimal_places=6, default=1)
    base_currency_amount = models.DecimalField(max_digits=18, decimal_places=2)
    ugx_amount_efris = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    amount_paid = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    balance_due = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="draft")
    efris_fiscal_number = models.CharField(max_length=100, blank=True)
    efris_ack_reference = models.CharField(max_length=100, blank=True)
    due_date = models.DateField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    is_void = models.BooleanField(default=False)
    void_reason = models.TextField(blank=True)
    voided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='voided_fee_notes',
    )
    voided_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='created_fee_notes',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.fee_note_number


class FeeNoteReminder(models.Model):
    fee_note = models.ForeignKey(FeeNote, on_delete=models.CASCADE, related_name='reminders')
    sent_at = models.DateTimeField(auto_now_add=True)
    reminder_type = models.CharField(max_length=20)
    sent_to = models.EmailField()
    success = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    def __str__(self):
        return f"Reminder for {self.fee_note} at {self.sent_at}"
