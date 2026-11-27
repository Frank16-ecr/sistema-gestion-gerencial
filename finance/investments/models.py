from django.conf import settings
from django.db import models

from tenants.config import default_currency


class Investment(models.Model):
    TYPE_CHOICES = [
        ("stock", "Acciones"),
        ("bond", "Bonos"),
        ("fund", "Fondo"),
        ("term_deposit", "Deposito a plazo"),
        ("real_estate", "Inmueble"),
        ("other", "Otro"),
    ]
    STATUS_CHOICES = [
        ("active", "Activa"),
        ("matured", "Vencida"),
        ("sold", "Liquidada"),
    ]
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, related_name='investments')
    name = models.CharField(max_length=255)
    asset_type = models.CharField(max_length=30, choices=TYPE_CHOICES, default="other")
    institution = models.CharField(max_length=255, blank=True)
    currency = models.CharField(max_length=10, default=default_currency)
    initial_amount = models.DecimalField(max_digits=18, decimal_places=2)
    start_date = models.DateField()
    maturity_date = models.DateField(null=True, blank=True)
    expected_return_rate = models.DecimalField(
        max_digits=7, decimal_places=4, null=True, blank=True,
        help_text="Rendimiento anual esperado en porcentaje.",
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='created_investments',
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-start_date', 'name']

    def __str__(self):
        return f"{self.name} ({self.initial_amount} {self.currency})"


class InvestmentMovement(models.Model):
    TYPE_CHOICES = [
        ("contribution", "Aporte"),
        ("return", "Rendimiento"),
        ("withdrawal", "Retiro"),
        ("fee", "Comision"),
    ]
    investment = models.ForeignKey(Investment, on_delete=models.CASCADE, related_name='movements')
    movement_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    movement_date = models.DateField()
    notes = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-movement_date', '-id']

    def __str__(self):
        return f"{self.movement_type} {self.amount} on {self.movement_date}"
