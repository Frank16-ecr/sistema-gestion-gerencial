"""Ayudas compartidas por todas las pantallas del panel."""
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404
from django.utils.http import url_has_allowed_host_and_scheme

from finance.security.permissions import has_tenant_role

from .access import SESSION_KEY, accessible_tenants, can_write, current_tenant

# Los sueldos son sensibles: solo estos roles ven la nomina.
PAYROLL_ROLES = ('admin', 'manager', 'auditor')


def context(request, obj_tenant=None, **extra):
    """Contexto comun. Si se ve un objeto de otra empresa, esa pasa a ser la seleccionada."""
    if obj_tenant is not None:
        request.session[SESSION_KEY] = obj_tenant.id
    tenant, tenants = current_tenant(request)
    return {
        'tenant': tenant,
        'tenants': tenants,
        'can_write': can_write(request.user, tenant),
        'can_payroll': bool(tenant) and has_tenant_role(request.user, tenant.id, PAYROLL_ROLES),
        **extra,
    }


def require_write(request, tenant):
    if not can_write(request.user, tenant):
        raise PermissionDenied('No tienes permiso de escritura en esta empresa.')


def require_payroll(request, tenant):
    if not tenant or not has_tenant_role(request.user, tenant.id, PAYROLL_ROLES):
        raise PermissionDenied('No tienes permiso para ver la nómina de esta empresa.')


def scoped_object(request, queryset, pk, path='tenant'):
    """Objeto por pk, solo si pertenece a una empresa accesible; si no, 404."""
    return get_object_or_404(queryset, pk=pk, **{f'{path}__in': accessible_tenants(request.user)})


def form_errors(form):
    return ' '.join(f'{form.fields[f].label or f}: {" ".join(e)}' if f in form.fields else ' '.join(e)
                    for f, e in form.errors.items())


def safe_next(request, default):
    """Destino de redireccion: el `next` enviado si es interno, si no `default` (nombre de url)."""
    next_url = request.POST.get('next', '')
    if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        return next_url
    return default
