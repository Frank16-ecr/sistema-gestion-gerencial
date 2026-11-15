"""Que empresas puede ver un usuario y cual esta seleccionada en el panel."""
from finance.security.permissions import user_tenant_ids
from tenants.models import Tenant

SESSION_KEY = 'panel_tenant_id'


def accessible_tenants(user):
    """Superusuarios ven todas las empresas activas; el resto, las de sus roles activos."""
    qs = Tenant.objects.filter(is_active=True)
    if user.is_superuser:
        return qs.order_by('name')
    return qs.filter(id__in=user_tenant_ids(user)).order_by('name')


def current_tenant(request):
    """Empresa seleccionada (?tenant=ID o la guardada en sesion); None si no tiene acceso a ninguna."""
    tenants = list(accessible_tenants(request.user))
    by_id = {t.id: t for t in tenants}
    requested = request.GET.get('tenant') or request.session.get(SESSION_KEY)
    try:
        chosen = by_id.get(int(requested))
    except (TypeError, ValueError):
        chosen = None
    chosen = chosen or (tenants[0] if tenants else None)
    if chosen:
        request.session[SESSION_KEY] = chosen.id
    return chosen, tenants
