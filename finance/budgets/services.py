from decimal import Decimal

from django.db.models import Sum

from finance.expenses.models import Expense

SPENT_STATUSES = ('approved', 'paid')


def budget_execution(budget):
    """Presupuesto vs. gasto real (gastos aprobados o pagados en el periodo)."""
    spent_rows = (
        Expense.objects.filter(
            tenant=budget.tenant,
            currency=budget.currency,
            status__in=SPENT_STATUSES,
            expense_date__range=(budget.period_start, budget.period_end),
        )
        .values('category')
        .annotate(total=Sum('amount'))
    )
    spent = {row['category']: row['total'] or Decimal('0') for row in spent_rows}

    lines, total_planned, total_spent = [], Decimal('0'), Decimal('0')
    planned_categories = set()
    for line in budget.lines.all():
        planned_categories.add(line.category)
        real = spent.get(line.category, Decimal('0'))
        total_planned += line.planned_amount
        total_spent += real
        lines.append({
            'category': line.category,
            'planned': line.planned_amount,
            'spent': real,
            'remaining': line.planned_amount - real,
            'percent_used': round(real / line.planned_amount * 100, 2) if line.planned_amount else None,
            'over_budget': real > line.planned_amount,
        })

    unbudgeted = {c: v for c, v in spent.items() if c not in planned_categories}
    total_spent += sum(unbudgeted.values(), Decimal('0'))

    return {
        'budget': budget.id,
        'name': budget.name,
        'currency': budget.currency,
        'total_planned': total_planned,
        'total_spent': total_spent,
        'total_remaining': total_planned - total_spent,
        'percent_used': round(total_spent / total_planned * 100, 2) if total_planned else None,
        'lines': lines,
        'unbudgeted_spending': unbudgeted,
    }
