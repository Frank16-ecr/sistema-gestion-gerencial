from django.db import models
from django.conf import settings


class ExchangeRate(models.Model):
    SOURCE_CHOICES = [
        ("manual", "Manual"),
        ("automatic", "Automatic"),
    ]
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, related_name='exchange_rates')
    from_currency = models.CharField(max_length=10)
    to_currency = models.CharField(max_length=10, default="UGX")
    rate = models.DecimalField(max_digits=18, decimal_places=6)
    rate_date = models.DateField()
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default="manual")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("tenant", "from_currency", "to_currency", "rate_date")
        ordering = ["-rate_date"]

    def __str__(self):
        return f"{self.from_currency}/{self.to_currency} = {self.rate} on {self.rate_date}"
