from rest_framework import viewsets

from finance.security.permissions import TenantScopedMixin

from .models import AuditLog
from .serializers import AuditLogSerializer

# Solo administracion, gerencia y auditoria consultan la bitacora.
AUDIT_ROLES = ('admin', 'manager', 'auditor')


class AuditLogViewSet(TenantScopedMixin, viewsets.ReadOnlyModelViewSet):
    queryset = AuditLog.objects.all()
    read_roles = AUDIT_ROLES
    serializer_class = AuditLogSerializer
    filterset_fields = ('tenant', 'action', 'model_name', 'performed_by')
    search_fields = ('model_name', 'object_id', 'notes')
