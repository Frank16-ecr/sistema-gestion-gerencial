from django.db import models
from django.conf import settings


class AuditLog(models.Model):
    ACTION_CHOICES = [
        ("create", "Create"),
        ("update", "Update"),
        ("delete", "Delete"),
        ("void", "Void"),
        ("approve", "Approve"),
        ("submit_efris", "Submit to EFRIS"),
        ("ack_efris", "Acknowledge EFRIS"),
        ("send_email", "Send Email"),
        ("fx_override", "FX Rate Override"),
    ]
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, related_name='audit_logs')
    action = models.CharField(max_length=30, choices=ACTION_CHOICES)
    model_name = models.CharField(max_length=100)
    object_id = models.CharField(max_length=50)
    before_value = models.JSONField(null=True, blank=True)
    after_value = models.JSONField(null=True, blank=True)
    performed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.action} on {self.model_name}#{self.object_id} at {self.created_at}"

    class Meta:
        ordering = ['-created_at']
