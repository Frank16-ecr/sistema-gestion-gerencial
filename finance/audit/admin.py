from django.contrib import admin
from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('action', 'model_name', 'object_id', 'performed_by', 'tenant', 'ip_address', 'created_at')
    search_fields = ('model_name', 'object_id', 'notes')
    list_filter = ('action', 'model_name', 'tenant')
    date_hierarchy = 'created_at'
    readonly_fields = ('action', 'model_name', 'object_id', 'before_value', 'after_value', 'performed_by', 'ip_address', 'notes', 'created_at', 'tenant')
