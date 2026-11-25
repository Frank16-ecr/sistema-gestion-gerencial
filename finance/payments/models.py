from django.conf import settings
from django.db import models


class FeeNotePayment(models.Model):
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, related_name='payments')
    fee_note = models.ForeignKey("finance_invoicing.FeeNote", on_delete=models.CASCADE, related_name="payments")
    payment_currency = models.CharField(max_length=10)
    amount_received_foreign = models.DecimalField(max_digits=18, decimal_places=2)
    exchange_rate = models.DecimalField(max_digits=18, decimal_places=6, default=1)
    base_currency_received = models.DecimalField(max_digits=18, decimal_places=2)
    fx_gain_loss = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    payment_date = models.DateField()
    payment_method = models.CharField(max_length=30)
    bank_reference = models.CharField(max_length=100, blank=True)
    wht_deducted = models.BooleanField(default=False)
    wht_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    wht_cert_number = models.CharField(max_length=100, blank=True)
    proof_file = models.FileField(upload_to="finance/payments/", blank=True, null=True)
    efris_receipt_ref = models.CharField(max_length=100, blank=True)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Payment for {self.fee_note} on {self.payment_date}"


class WHTCredit(models.Model):
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, related_name='wht_credits')
    payment = models.OneToOneField(FeeNotePayment, on_delete=models.CASCADE, related_name='wht_credit')
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    cert_number = models.CharField(max_length=100)
    period_year = models.PositiveIntegerField()
    period_month = models.PositiveIntegerField()
    is_utilised = models.BooleanField(default=False)
    utilised_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"WHT Credit {self.cert_number} ({self.amount})"
