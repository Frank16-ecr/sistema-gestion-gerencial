from rest_framework.permissions import SAFE_METHODS, BasePermission

from .models import UserTenantRole


class IsManagerOrReadOnly(BasePermission):
    """Lectura para cualquier usuario autenticado.

    Escritura solo para superusuarios o usuarios con rol admin/manager
    activo en alguna empresa.
    """

    write_roles = ("admin", "manager")

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if request.method in SAFE_METHODS:
            return True
        if user.is_superuser:
            return True
        return UserTenantRole.objects.filter(
            user=user, is_active=True, role__in=self.write_roles
        ).exists()
