from django.conf import settings
from django.db import models


class Budget(models.Model):
    STATUS_CHOICES = [
        ("draft", "Borrador"),
        ("approved", "Aprobado"),
        ("closed", "Cerrado"),
    ]
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, related_name='budgets')
    name = models.CharField(max_length=255)
    fiscal_year = models.PositiveIntegerField()
    period_start = models.DateField()
    period_end = models.DateField()
    currency = models.CharField(max_length=10, default="USD")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="draft")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='created_budgets',
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='approved_budgets',
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("tenant", "name", "fiscal_year")
        ordering = ['-fiscal_year', 'name']

    def __str__(self):
        return f"{self.name} {self.fiscal_year}"


class BudgetLine(models.Model):
    """Monto planificado por categoria de gasto (mismas categorias de expenses)."""

    budget = models.ForeignKey(Budget, on_delete=models.CASCADE, related_name='lines')
    category = models.CharField(max_length=50)
    planned_amount = models.DecimalField(max_digits=18, decimal_places=2)
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        unique_together = ("budget", "category")

    def __str__(self):
        return f"{self.budget} - {self.category}: {self.planned_amount}"
