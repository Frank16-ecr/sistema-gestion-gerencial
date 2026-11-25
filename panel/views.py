from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from rest_framework.exceptions import ValidationError

from finance.expenses.models import Expense
from finance.reports.services import ReportService
from finance.reports.views import dashboard_period
from finance.security.permissions import user_tenant_ids
from finance.statutory.models import StatutoryObligation
from tenants.models import Tenant


def _user_tenants(user):
    qs = Tenant.objects.filter(is_active=True).order_by('name')
    if not user.is_superuser:
        qs = qs.filter(pk__in=user_tenant_ids(user))
    return list(qs)


def _error_messages(detail):
    """Aplana el detalle de un ValidationError de DRF a una lista de textos."""
    if isinstance(detail, dict):
        return [msg for value in detail.values() for msg in _error_messages(value)]
    if isinstance(detail, (list, tuple)):
        return [msg for value in detail for msg in _error_messages(value)]
    return [str(detail)]


EXPENSE_LABELS = dict(Expense.CATEGORY_CHOICES)
OBLIGATION_LABELS = dict(StatutoryObligation.OBLIGATION_TYPES)


def _add_labels(data):
    """Nombres legibles en lugar de los codigos internos."""
    for row in data['expenses']['by_currency'].values():
        row['by_category'] = {EXPENSE_LABELS.get(k, k): v for k, v in row['by_category'].items()}
    for budget in data['budgets']:
        for line in budget['lines']:
            line['label'] = EXPENSE_LABELS.get(line['category'], line['category'])
    for ob in data['obligations']['upcoming']:
        ob['label'] = OBLIGATION_LABELS.get(ob['obligation_type'], ob['obligation_type'])


def _percent_width(value):
    """Ancho de la barra de progreso (0-100)."""
    if value is None:
        return 0
    return max(0, min(100, float(value)))


@login_required
def dashboard(request):
    tenants = _user_tenants(request.user)
    context = {'tenants': tenants, 'tenant': None, 'data': None, 'errors': []}
    if not tenants:
        return render(request, 'panel/dashboard.html', context)

    selected = request.GET.get('tenant')
    tenant = next((t for t in tenants if str(t.pk) == selected), tenants[0])
    try:
        start_date, end_date = dashboard_period(request.GET)
    except ValidationError as exc:
        context['errors'] = _error_messages(exc.detail)
        start_date, end_date = dashboard_period({})

    data = ReportService.get_management_dashboard(tenant, start_date, end_date)
    _add_labels(data)
    for budget in data['budgets']:
        budget['bar_width'] = _percent_width(budget['percent_used'])
        for line in budget['lines']:
            line['bar_width'] = _percent_width(line['percent_used'])

    context.update(tenant=tenant, data=data, start_date=start_date, end_date=end_date)
    return render(request, 'panel/dashboard.html', context)
