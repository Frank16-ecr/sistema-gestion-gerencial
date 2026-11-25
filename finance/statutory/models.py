from django.db import models


class StatutoryObligation(models.Model):
    OBLIGATION_TYPES = [
        ("paye", "PAYE (retención de renta)"),
        ("nssf", "NSSF (seguridad social)"),
        ("vat", "IVA"),
        ("income_tax", "Impuesto sobre la renta"),
        ("wht", "Retención en la fuente"),
        ("social_security", "Seguridad social"),
        # Venezuela
        ("islr", "ISLR (retención a trabajadores)"),
        ("ivss", "IVSS (Seguro Social)"),
        ("rpe", "RPE (paro forzoso)"),
        ("faov", "FAOV (vivienda)"),
        ("inces", "INCES"),
        ("pension", "Protección de Pensiones"),
        ("iva", "IVA"),
        ("igtf", "IGTF"),
        ("other", "Otra obligacion"),
    ]
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("filed", "Filed"),
        ("paid", "Paid"),
        ("overdue", "Overdue"),
    ]
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, related_name='statutory_obligations')
    obligation_type = models.CharField(max_length=30, choices=OBLIGATION_TYPES)
    period_month = models.PositiveIntegerField()
    period_year = models.PositiveIntegerField()
    amount_due = models.DecimalField(max_digits=18, decimal_places=2)
    due_date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    filed_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    payment_reference = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("tenant", "obligation_type", "period_month", "period_year")

    def __str__(self):
        return f"{self.obligation_type} - {self.period_year}/{self.period_month:02d} ({self.tenant})"
