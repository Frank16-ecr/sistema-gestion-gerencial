from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import SAFE_METHODS, BasePermission

from .models import UserTenantRole

WRITE_ROLES = ("admin", "manager")
ALL_ROLES = ("admin", "manager", "analyst", "auditor", "viewer")


def user_tenant_ids(user, roles=ALL_ROLES):
    """Ids de las empresas donde el usuario tiene un rol activo."""
    return list(
        UserTenantRole.objects.filter(user=user, is_active=True, role__in=roles)
        .values_list('tenant_id', flat=True)
    )


def has_tenant_role(user, tenant_id, roles=ALL_ROLES):
    if user.is_superuser:
        return True
    if tenant_id is None:
        return False
    return UserTenantRole.objects.filter(
        user=user, tenant_id=tenant_id, is_active=True, role__in=roles
    ).exists()


def object_tenant_id(obj):
    """Empresa a la que pertenece un objeto, directamente o por su padre."""
    if hasattr(obj, 'tenant_id'):
        return obj.tenant_id
    for relation in ('budget', 'investment'):
        parent = getattr(obj, relation, None)
        if parent is not None:
            return parent.tenant_id
    return None


class IsManagerOrReadOnly(BasePermission):
    """Acceso por empresa.

    - Lectura: rol activo (cualquiera) en la empresa del objeto.
    - Escritura: rol admin o manager en la empresa del objeto.
    - Superusuarios: acceso total.

    A nivel de lista/creacion solo exige que el usuario tenga algun rol de
    escritura; la comprobacion por empresa la hacen has_object_permission y
    TenantScopedMixin.
    """

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser:
            return True
        roles = ALL_ROLES if request.method in SAFE_METHODS else WRITE_ROLES
        return bool(user_tenant_ids(user, roles))

    def has_object_permission(self, request, view, obj):
        roles = ALL_ROLES if request.method in SAFE_METHODS else WRITE_ROLES
        return has_tenant_role(request.user, object_tenant_id(obj), roles)


class TenantScopedMixin:
    """Limita los listados a las empresas del usuario y valida la escritura.

    `tenant_path` indica como llegar a la empresa desde el modelo
    ('tenant', 'budget__tenant', 'investment__tenant').
    """

    tenant_path = 'tenant'

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if user.is_superuser:
            return qs
        return qs.filter(**{f'{self.tenant_path}__in': user_tenant_ids(user)})

    @staticmethod
    def _validated_tenant_id(validated_data):
        if 'tenant' in validated_data:
            return validated_data['tenant'].pk
        for relation in ('budget', 'investment'):
            if relation in validated_data:
                return validated_data[relation].tenant_id
        return None

    def _check_write_target(self, serializer):
        tenant_id = self._validated_tenant_id(serializer.validated_data)
        if tenant_id is not None and not has_tenant_role(self.request.user, tenant_id, WRITE_ROLES):
            raise PermissionDenied("No tienes permiso de escritura en esa empresa.")

    def perform_create(self, serializer):
        self._check_write_target(serializer)
        extra = {'created_by': self.request.user} if hasattr(serializer.Meta.model, 'created_by') else {}
        serializer.save(**extra)

    def perform_update(self, serializer):
        self._check_write_target(serializer)
        serializer.save()
