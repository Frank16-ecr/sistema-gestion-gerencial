from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from finance.budgets.models import Budget
from finance.budgets.services import budget_execution
from finance.expenses.models import Expense
from finance.investments.models import Investment, InvestmentMovement
from finance.investments.services import investment_summary, portfolio_summary

from .access import accessible_tenants, current_tenant
from .charts import execution_chart, investment_timeline, label_for, monthly_spending, portfolio_by_type
from .common import context as _context, form_errors as _form_errors, require_write as _require_write
from .forms import BudgetForm, BudgetLineFormSet, BudgetLineFormSetNew, ExpenseForm, InvestmentForm, MovementForm

STATUS_ES = [('pending', 'Pendiente'), ('approved', 'Aprobado'), ('paid', 'Pagado'), ('rejected', 'Rechazado')]
CATEGORY_FILTER = [
    ('rent', 'Alquiler'), ('internet', 'Internet'), ('fuel', 'Combustible'),
    ('audit_fees', 'Honorarios de auditoría'), ('utilities', 'Servicios'),
    ('office_supplies', 'Insumos de oficina'), ('travel', 'Viajes'), ('other', 'Otros'),
]


# --------------------------------------------------------------------------- helpers

def _with_labels(execution):
    for line in execution['lines']:
        line['label'] = label_for(line['category'])
    execution['unbudgeted'] = [
        {'label': label_for(cat), 'spent': amount} for cat, amount in execution['unbudgeted_spending'].items()
    ]
    return execution


def _get_budget(request, pk):
    return get_object_or_404(
        Budget.objects.select_related('tenant', 'approved_by').prefetch_related('lines'),
        pk=pk, tenant__in=accessible_tenants(request.user),
    )


def _get_investment(request, pk):
    return get_object_or_404(
        Investment.objects.select_related('tenant').prefetch_related('movements'),
        pk=pk, tenant__in=accessible_tenants(request.user),
    )


def _get_expense(request, pk):
    return get_object_or_404(Expense.objects.select_related('tenant'), pk=pk,
                             tenant__in=accessible_tenants(request.user))


# --------------------------------------------------------------------------- resumen

@login_required
def home(request):
    ctx = _context(request, section='home')
    tenant = ctx['tenant']
    if not tenant:
        return render(request, 'panel/home.html', ctx)

    budgets = Budget.objects.filter(tenant=tenant).prefetch_related('lines')
    featured = budgets.filter(status='approved').order_by('-fiscal_year', '-period_start').first() \
        or budgets.order_by('-fiscal_year', '-period_start').first()
    investments = Investment.objects.filter(tenant=tenant)
    expenses = Expense.objects.filter(tenant=tenant)
    execution = _with_labels(budget_execution(featured)) if featured else None

    ctx.update(
        budget_count=budgets.count(),
        draft_count=budgets.filter(status='draft').count(),
        featured_budget=featured,
        featured_execution=execution,
        investment_count=investments.filter(status='active').count(),
        portfolio=portfolio_summary(investments),
        pending_expenses=expenses.filter(status='pending').count(),
        recent_expenses=expenses.order_by('-expense_date', '-id')[:6],
        chart_execution=execution_chart(execution) if execution else None,
        chart_monthly=monthly_spending(featured) if featured else None,
        chart_portfolio=portfolio_by_type(investments),
    )
    return render(request, 'panel/home.html', ctx)


# --------------------------------------------------------------------------- presupuestos

@login_required
def budget_list(request):
    ctx = _context(request, section='budgets')
    if ctx['tenant']:
        rows = []
        for budget in Budget.objects.filter(tenant=ctx['tenant']).prefetch_related('lines'):
            execution = budget_execution(budget)
            rows.append({'budget': budget, 'execution': execution})
        ctx['rows'] = rows
    return render(request, 'panel/budget_list.html', ctx)


@login_required
def budget_detail(request, pk):
    budget = _get_budget(request, pk)
    ctx = _context(request, obj_tenant=budget.tenant, section='budgets')
    execution = _with_labels(budget_execution(budget))
    ctx.update(
        budget=budget, execution=execution,
        chart_execution=execution_chart(execution), chart_monthly=monthly_spending(budget),
        editable=ctx['can_write'] and budget.status == 'draft',
    )
    return render(request, 'panel/budget_detail.html', ctx)


def _budget_form(request, budget, creating):
    tenant = budget.tenant
    formset_class = BudgetLineFormSetNew if creating else BudgetLineFormSet
    if request.method == 'POST':
        form = BudgetForm(request.POST, instance=budget, tenant=tenant)
        formset = formset_class(request.POST, instance=budget, prefix='lines')
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                form.save()
                formset.save()
            messages.success(request, 'Presupuesto creado.' if creating else 'Presupuesto actualizado.')
            return redirect('panel:budget-detail', pk=budget.pk)
        messages.error(request, 'Revisa los campos marcados.')
    else:
        form = BudgetForm(instance=budget, tenant=tenant)
        formset = formset_class(instance=budget, prefix='lines')
    ctx = _context(request, obj_tenant=tenant, section='budgets', form=form, formset=formset,
                   creating=creating, budget=budget)
    return render(request, 'panel/budget_form.html', ctx)


@login_required
def budget_create(request):
    tenant, _ = current_tenant(request)
    _require_write(request, tenant)
    return _budget_form(request, Budget(tenant=tenant, created_by=request.user), creating=True)


@login_required
def budget_edit(request, pk):
    budget = _get_budget(request, pk)
    _require_write(request, budget.tenant)
    if budget.status != 'draft':
        messages.error(request, 'Solo se pueden editar presupuestos en borrador.')
        return redirect('panel:budget-detail', pk=pk)
    return _budget_form(request, budget, creating=False)


@login_required
@require_POST
def budget_action(request, pk, action):
    budget = _get_budget(request, pk)
    _require_write(request, budget.tenant)
    if action == 'approve':
        if budget.status != 'draft':
            messages.error(request, 'Solo se aprueban presupuestos en borrador.')
        elif not budget.lines.exists():
            messages.error(request, 'Agrega al menos una categoría antes de aprobar.')
        else:
            budget.status, budget.approved_by, budget.approved_at = 'approved', request.user, timezone.now()
            budget.save(update_fields=['status', 'approved_by', 'approved_at'])
            messages.success(request, 'Presupuesto aprobado.')
    elif action == 'close':
        if budget.status != 'approved':
            messages.error(request, 'Solo se cierran presupuestos aprobados.')
        else:
            budget.status = 'closed'
            budget.save(update_fields=['status'])
            messages.success(request, 'Presupuesto cerrado.')
    elif action == 'delete':
        if budget.status != 'draft':
            messages.error(request, 'Solo se eliminan presupuestos en borrador.')
        else:
            budget.delete()
            messages.success(request, 'Presupuesto eliminado.')
            return redirect('panel:budgets')
    else:
        messages.error(request, 'Acción desconocida.')
    return redirect('panel:budget-detail', pk=pk)


# --------------------------------------------------------------------------- gastos

@login_required
def expense_list(request):
    ctx = _context(request, section='expenses')
    tenant = ctx['tenant']
    if tenant:
        expenses = Expense.objects.filter(tenant=tenant)
        status, category = request.GET.get('status', ''), request.GET.get('category', '')
        if status:
            expenses = expenses.filter(status=status)
        if category:
            expenses = expenses.filter(category=category)
        counts = {row['status']: row for row in
                  Expense.objects.filter(tenant=tenant).values('status').annotate(n=Count('id'), total=Sum('amount'))}
        status_cards = [
            {'code': code, 'label': label, 'n': counts.get(code, {}).get('n', 0),
             'total': counts.get(code, {}).get('total') or 0}
            for code, label in STATUS_ES
        ]
        ctx.update(
            expenses=expenses.select_related('submitted_by').order_by('-expense_date', '-id')[:300],
            status=status, category=category, category_choices=CATEGORY_FILTER,
            status_choices=STATUS_ES, status_cards=status_cards,
        )
    return render(request, 'panel/expense_list.html', ctx)


@login_required
def expense_create(request):
    tenant, _ = current_tenant(request)
    _require_write(request, tenant)
    expense = Expense(tenant=tenant, submitted_by=request.user, status='pending')
    form = ExpenseForm(request.POST or None, instance=expense, tenant=tenant)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Gasto registrado.')
        return redirect('panel:expenses')
    return render(request, 'panel/expense_form.html', _context(request, section='expenses', form=form))


@login_required
@require_POST
def expense_action(request, pk, action):
    expense = _get_expense(request, pk)
    _require_write(request, expense.tenant)
    transitions = {
        'approve': ({'pending'}, 'approved', 'Gasto aprobado.'),
        'pay': ({'approved'}, 'paid', 'Gasto marcado como pagado.'),
        'reject': ({'pending', 'approved'}, 'rejected', 'Gasto rechazado.'),
    }
    if action in transitions:
        allowed, new_status, text = transitions[action]
        if expense.status not in allowed:
            messages.error(request, 'Ese cambio de estado no es válido para este gasto.')
        else:
            expense.status = new_status
            if new_status == 'approved':
                expense.approved_by, expense.approved_at = request.user, timezone.now()
            expense.save()
            messages.success(request, text)
    elif action == 'delete':
        if expense.status in ('pending', 'rejected'):
            expense.delete()
            messages.success(request, 'Gasto eliminado.')
        else:
            messages.error(request, 'Solo se eliminan gastos pendientes o rechazados.')
    else:
        messages.error(request, 'Acción desconocida.')
    next_url = request.POST.get('next', '')
    if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        return redirect(next_url)
    return redirect('panel:expenses')


# --------------------------------------------------------------------------- inversiones

@login_required
def investment_list(request):
    ctx = _context(request, section='investments')
    if ctx['tenant']:
        investments = Investment.objects.filter(tenant=ctx['tenant']).prefetch_related('movements')
        ctx['rows'] = [{'investment': i, 'summary': investment_summary(i)} for i in investments]
        ctx['portfolio'] = portfolio_summary(Investment.objects.filter(tenant=ctx['tenant']))
        ctx['chart_portfolio'] = portfolio_by_type(Investment.objects.filter(tenant=ctx['tenant']))
    return render(request, 'panel/investment_list.html', ctx)


@login_required
def investment_detail(request, pk):
    investment = _get_investment(request, pk)
    ctx = _context(request, obj_tenant=investment.tenant, section='investments')
    ctx.update(
        investment=investment, summary=investment_summary(investment),
        movements=sorted(investment.movements.all(), key=lambda m: (m.movement_date, m.id), reverse=True),
        chart_timeline=investment_timeline(investment),
        movement_form=MovementForm(initial={'movement_date': timezone.localdate()}),
    )
    return render(request, 'panel/investment_detail.html', ctx)


def _investment_form(request, investment, creating):
    tenant = investment.tenant
    form = InvestmentForm(request.POST or None, instance=investment, tenant=tenant)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Inversión creada.' if creating else 'Inversión actualizada.')
        return redirect('panel:investment-detail', pk=investment.pk)
    ctx = _context(request, obj_tenant=tenant, section='investments', form=form, creating=creating,
                   investment=investment)
    return render(request, 'panel/investment_form.html', ctx)


@login_required
def investment_create(request):
    tenant, _ = current_tenant(request)
    _require_write(request, tenant)
    return _investment_form(request, Investment(tenant=tenant, created_by=request.user), creating=True)


@login_required
def investment_edit(request, pk):
    investment = _get_investment(request, pk)
    _require_write(request, investment.tenant)
    return _investment_form(request, investment, creating=False)


@login_required
@require_POST
def investment_delete(request, pk):
    investment = _get_investment(request, pk)
    _require_write(request, investment.tenant)
    investment.delete()
    messages.success(request, 'Inversión eliminada junto con sus movimientos.')
    return redirect('panel:investments')


@login_required
@require_POST
def movement_add(request, pk):
    investment = _get_investment(request, pk)
    _require_write(request, investment.tenant)
    form = MovementForm(request.POST, instance=InvestmentMovement(investment=investment))
    if form.is_valid():
        form.save()
        messages.success(request, 'Movimiento registrado.')
    else:
        messages.error(request, 'No se pudo registrar el movimiento. ' + _form_errors(form))
    return redirect('panel:investment-detail', pk=pk)


@login_required
@require_POST
def movement_delete(request, pk, movement_pk):
    investment = _get_investment(request, pk)
    _require_write(request, investment.tenant)
    get_object_or_404(InvestmentMovement, pk=movement_pk, investment=investment).delete()
    messages.success(request, 'Movimiento eliminado.')
    return redirect('panel:investment-detail', pk=pk)
