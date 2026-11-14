from django.db import models


class Tenant(models.Model):
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class TenantSetting(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='settings')
    setting_key = models.CharField(max_length=100)
    setting_value = models.JSONField()
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("tenant", "setting_key")

    def __str__(self):
        return f"{self.tenant.name} - {self.setting_key}"
