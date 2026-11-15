"""Datos listos para los graficos del panel (todo como numeros simples, serializables a JSON)."""
from collections import defaultdict
from decimal import Decimal

from finance.expenses.models import Expense
from finance.investments.services import investment_summary

from .forms import CATEGORY_LABELS

MONTHS = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic']


def _f(value):
    return float(value or Decimal('0'))


def label_for(category):
    return CATEGORY_LABELS.get(category, category)


def execution_chart(execution):
    """Planificado vs gastado por categoria (incluye lo no presupuestado)."""
    labels, planned, spent = [], [], []
    for line in execution['lines']:
        labels.append(label_for(line['category']))
        planned.append(_f(line['planned']))
        spent.append(_f(line['spent']))
    for category, amount in execution['unbudgeted_spending'].items():
        labels.append(f'{label_for(category)} (sin presupuestar)')
        planned.append(0)
        spent.append(_f(amount))
    return {'labels': labels, 'planned': planned, 'spent': spent, 'currency': execution['currency']}


def monthly_spending(budget):
    """Gasto real (aprobado o pagado) por mes dentro del periodo del presupuesto."""
    rows = Expense.objects.filter(
        tenant=budget.tenant, currency=budget.currency, status__in=['approved', 'paid'],
        expense_date__range=(budget.period_start, budget.period_end),
    ).values_list('expense_date', 'amount')
    totals = defaultdict(Decimal)
    for day, amount in rows:
        totals[(day.year, day.month)] += amount

    labels, values = [], []
    year, month = budget.period_start.year, budget.period_start.month
    while (year, month) <= (budget.period_end.year, budget.period_end.month):
        labels.append(f'{MONTHS[month - 1]} {str(year)[2:]}')
        values.append(_f(totals.get((year, month))))
        month += 1
        if month > 12:
            year, month = year + 1, 1
    return {'labels': labels, 'values': values, 'currency': budget.currency}


def portfolio_by_type(investments):
    """Saldo actual de las inversiones activas por tipo de activo, separado por moneda."""
    result = defaultdict(lambda: defaultdict(Decimal))
    for inv in investments.filter(status='active').prefetch_related('movements'):
        result[inv.currency][inv.get_asset_type_display()] += investment_summary(inv)['current_balance']
    return {
        currency: {'labels': list(rows.keys()), 'values': [_f(v) for v in rows.values()]}
        for currency, rows in result.items()
    }


def investment_timeline(investment):
    """Evolucion del saldo: monto inicial y luego cada movimiento acumulado."""
    sign = {'contribution': 1, 'return': 1, 'withdrawal': -1, 'fee': -1}
    balance = investment.initial_amount
    points = [(investment.start_date.isoformat(), _f(balance))]
    for move in sorted(investment.movements.all(), key=lambda m: (m.movement_date, m.id)):
        balance += sign[move.movement_type] * move.amount
        points.append((move.movement_date.isoformat(), _f(balance)))
    return {'labels': [p[0] for p in points], 'values': [p[1] for p in points], 'currency': investment.currency}
