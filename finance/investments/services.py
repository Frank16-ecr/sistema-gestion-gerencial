from decimal import Decimal

MOVEMENT_TYPES = ('contribution', 'return', 'withdrawal', 'fee')


def _totals(movements):
    totals = dict.fromkeys(MOVEMENT_TYPES, Decimal('0'))
    for m in movements:
        if m.movement_type in totals:
            totals[m.movement_type] += m.amount
    return totals


def investment_summary(investment):
    """Capital, rendimientos acumulados y saldo actual de una inversion."""
    t = _totals(investment.movements.all())
    capital = investment.initial_amount + t['contribution']
    return {
        'investment': investment.id,
        'currency': investment.currency,
        'initial_amount': investment.initial_amount,
        'contributions': t['contribution'],
        'returns': t['return'],
        'withdrawals': t['withdrawal'],
        'fees': t['fee'],
        'invested_capital': capital,
        'current_balance': capital + t['return'] - t['withdrawal'] - t['fee'],
        'net_return': t['return'] - t['fee'],
    }


def portfolio_by_currency(investments):
    """Resumen de inversiones agrupado por moneda (no mezcla monedas)."""
    result = {}
    for inv in investments.prefetch_related('movements'):
        summary = investment_summary(inv)
        row = result.setdefault(inv.currency, {
            'investments': 0, 'invested_capital': Decimal('0'), 'current_balance': Decimal('0'),
        })
        row['investments'] += 1
        row['invested_capital'] += summary['invested_capital']
        row['current_balance'] += summary['current_balance']
    return result
