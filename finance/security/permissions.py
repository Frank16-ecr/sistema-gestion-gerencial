from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import SAFE_METHODS, BasePermission

from .models import UserTenantRole

ADMIN_ROLES = ("admin",)
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


def _tenant_id_from_path(obj, tenant_path):
    """Sigue `tenant_path` ('tenant', 'budget__tenant', ...) hasta el id de la empresa."""
    if obj is None:
        return None
    *parents, last = tenant_path.split('__')
    for relation in parents:
        obj = getattr(obj, relation, None)
        if obj is None:
            return None
    if last == 'tenant':
        return getattr(obj, 'tenant_id', None)
    # El propio modelo es la empresa (tenant_path = 'pk').
    return getattr(obj, last, None)


def object_tenant_id(obj, tenant_path='tenant'):
    """Empresa a la que pertenece un objeto, directamente o por sus padres."""
    return _tenant_id_from_path(obj, tenant_path)


def _view_tenant_path(view):
    return getattr(view, 'tenant_path', 'tenant')


class TenantRolePermission(BasePermission):
    """Acceso por empresa segun el rol del usuario.

    - Lectura: cualquier rol activo en la empresa (`read_roles`).
    - Escritura: roles de `write_roles` (admin o gerente por defecto).
    - Superusuarios: acceso total.

    A nivel de lista/creacion solo exige que el usuario tenga algun rol del tipo
    necesario; la comprobacion por empresa la hacen has_object_permission y
    TenantScopedMixin.
    """

    read_roles = ALL_ROLES
    write_roles = WRITE_ROLES

    def _roles(self, request, view):
        if request.method in SAFE_METHODS:
            return getattr(view, 'read_roles', self.read_roles)
        return getattr(view, 'write_roles', self.write_roles)

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser:
            return True
        return bool(user_tenant_ids(user, self._roles(request, view)))

    def has_object_permission(self, request, view, obj):
        tenant_id = object_tenant_id(obj, _view_tenant_path(view))
        return has_tenant_role(request.user, tenant_id, self._roles(request, view))


# Nombre historico, usado por budgets e investments.
IsManagerOrReadOnly = TenantRolePermission


class TenantScopedMixin:
    """Limita los listados a las empresas del usuario y valida la escritura.

    `tenant_path` indica como llegar a la empresa desde el modelo
    ('tenant', 'budget__tenant', 'payroll_run__tenant', 'pk' para Tenant).
    Opcionalmente `read_roles` / `write_roles` ajustan los roles exigidos.
    """

    tenant_path = 'tenant'
    permission_classes = [TenantRolePermission]

    def get_queryset(self):
        qs = super().get_queryset()
        if not qs.ordered:
            # Paginacion estable: sin orden, una pagina puede repetir u omitir registros.
            qs = qs.order_by('-pk')
        user = self.request.user
        if user.is_superuser:
            return qs
        roles = getattr(self, 'read_roles', ALL_ROLES)
        lookup = 'pk' if self.tenant_path == 'pk' else self.tenant_path
        return qs.filter(**{f'{lookup}__in': user_tenant_ids(user, roles)})

    def _validated_tenant_id(self, validated_data, instance=None):
        """Empresa destino de una escritura segun los datos validados."""
        if self.tenant_path == 'pk':
            return instance.pk if instance is not None else None
        first, _, rest = self.tenant_path.partition('__')
        if first in validated_data:
            target = validated_data[first]
            if not rest:
                return target.pk
            return _tenant_id_from_path(target, rest)
        if instance is not None:
            return object_tenant_id(instance, self.tenant_path)
        return None

    def _check_write_target(self, serializer):
        roles = getattr(self, 'write_roles', WRITE_ROLES)
        tenant_id = self._validated_tenant_id(serializer.validated_data, serializer.instance)
        if not has_tenant_role(self.request.user, tenant_id, roles):
            raise PermissionDenied("No tienes permiso de escritura en esa empresa.")

    def creation_extra(self):
        """Campos que se rellenan con el usuario autenticado al crear."""
        model = self.get_serializer_class().Meta.model
        field_names = {f.name for f in model._meta.get_fields()}
        return {name: self.request.user for name in ('created_by', 'submitted_by') if name in field_names}

    def perform_create(self, serializer):
        self._check_write_target(serializer)
        extra = {k: v for k, v in self.creation_extra().items() if k not in serializer.validated_data}
        serializer.save(**extra)

    def perform_update(self, serializer):
        self._check_write_target(serializer)
        serializer.save()

    def check_tenant_access(self, tenant_id, roles=None):
        """Para acciones que reciben el id de empresa por parametro."""
        roles = roles or getattr(self, 'write_roles', WRITE_ROLES)
        if not has_tenant_role(self.request.user, tenant_id, roles):
            raise PermissionDenied("No tienes acceso a esa empresa.")
