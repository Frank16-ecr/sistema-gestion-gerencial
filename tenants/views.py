from rest_framework import viewsets

from finance.security.permissions import ADMIN_ROLES, TenantScopedMixin

from .models import Tenant, TenantSetting
from .serializers import TenantSerializer, TenantSettingSerializer


class TenantViewSet(TenantScopedMixin, viewsets.ModelViewSet):
    """Cada usuario ve solo sus empresas. Crear empresas es tarea de superusuarios;
    editarlas, de los administradores de cada una."""

    tenant_path = 'pk'
    write_roles = ADMIN_ROLES
    queryset = Tenant.objects.all()
    serializer_class = TenantSerializer
    search_fields = ('name', 'slug')
    filterset_fields = ('is_active',)


class TenantSettingViewSet(TenantScopedMixin, viewsets.ModelViewSet):
    write_roles = ADMIN_ROLES
    queryset = TenantSetting.objects.select_related('tenant')
    serializer_class = TenantSettingSerializer
    filterset_fields = ('tenant',)
