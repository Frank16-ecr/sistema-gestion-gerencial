from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render

from finance.budgets.models import Budget
from finance.budgets.services import budget_execution
from finance.investments.models import Investment
from finance.investments.services import investment_summary, portfolio_summary

from .access import current_tenant

CATEGORY_LABELS = {
    'rent': 'Alquiler',
    'internet': 'Internet',
    'fuel': 'Combustible',
    'audit_fees': 'Honorarios de auditoría',
    'utilities': 'Servicios',
    'office_supplies': 'Insumos de oficina',
    'travel': 'Viajes',
    'other': 'Otros',
}


def _label(category):
    return CATEGORY_LABELS.get(category, category)


def _context(request, **extra):
    tenant, tenants = current_tenant(request)
    return {'tenant': tenant, 'tenants': tenants, **extra}


def _with_labels(execution):
    for line in execution['lines']:
        line['label'] = _label(line['category'])
    execution['unbudgeted'] = [
        {'label': _label(cat), 'spent': amount} for cat, amount in execution['unbudgeted_spending'].items()
    ]
    return execution


@login_required
def home(request):
    ctx = _context(request, section='home')
    tenant = ctx['tenant']
    if tenant:
        budgets = Budget.objects.filter(tenant=tenant).prefetch_related('lines')
        featured = budgets.filter(status='approved').order_by('-fiscal_year', '-period_start').first() \
            or budgets.order_by('-fiscal_year', '-period_start').first()
        investments = Investment.objects.filter(tenant=tenant)
        ctx.update(
            budget_count=budgets.count(),
            featured_budget=featured,
            featured_execution=_with_labels(budget_execution(featured)) if featured else None,
            investment_count=investments.filter(status='active').count(),
            portfolio=portfolio_summary(investments),
        )
    return render(request, 'panel/home.html', ctx)


@login_required
def budget_list(request):
    ctx = _context(request, section='budgets')
    if ctx['tenant']:
        budgets = Budget.objects.filter(tenant=ctx['tenant']).prefetch_related('lines')
        ctx['rows'] = [
            {'budget': b, 'planned': sum(line.planned_amount for line in b.lines.all())} for b in budgets
        ]
    return render(request, 'panel/budget_list.html', ctx)


@login_required
def budget_detail(request, pk):
    ctx = _context(request, section='budgets')
    budget = get_object_or_404(
        Budget.objects.prefetch_related('lines'), pk=pk, tenant__in=ctx['tenants']
    )
    ctx.update(budget=budget, execution=_with_labels(budget_execution(budget)))
    return render(request, 'panel/budget_detail.html', ctx)


@login_required
def investment_list(request):
    ctx = _context(request, section='investments')
    if ctx['tenant']:
        investments = Investment.objects.filter(tenant=ctx['tenant']).prefetch_related('movements')
        ctx['rows'] = [{'investment': i, 'summary': investment_summary(i)} for i in investments]
        ctx['portfolio'] = portfolio_summary(Investment.objects.filter(tenant=ctx['tenant']))
    return render(request, 'panel/investment_list.html', ctx)


@login_required
def investment_detail(request, pk):
    ctx = _context(request, section='investments')
    investment = get_object_or_404(
        Investment.objects.prefetch_related('movements'), pk=pk, tenant__in=ctx['tenants']
    )
    ctx.update(investment=investment, summary=investment_summary(investment),
               movements=investment.movements.all())
    return render(request, 'panel/investment_detail.html', ctx)
