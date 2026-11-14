from django.conf import settings
from django.db import models


class UserTenantRole(models.Model):
    """Rol de un usuario dentro de una empresa (tenant)."""

    ROLE_CHOICES = [
        ("admin", "Administrador"),
        ("manager", "Gerente"),
        ("analyst", "Analista"),
        ("auditor", "Auditor"),
        ("viewer", "Solo lectura"),
    ]
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, related_name='user_roles')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='tenant_roles')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default="viewer")
    is_active = models.BooleanField(default=True)
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='assigned_roles',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("tenant", "user")

    def __str__(self):
        return f"{self.user} - {self.role} @ {self.tenant}"
