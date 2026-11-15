from decimal import Decimal


def _sum(movements, movement_type):
    return sum((m.amount for m in movements if m.movement_type == movement_type), Decimal('0'))


def investment_summary(inv):
    """Capital, rendimientos acumulados y saldo actual de una inversion."""
    movements = list(inv.movements.all())
    contributions = _sum(movements, 'contribution')
    returns = _sum(movements, 'return')
    withdrawals = _sum(movements, 'withdrawal')
    fees = _sum(movements, 'fee')
    capital = inv.initial_amount + contributions
    return {
        'investment': inv.id,
        'currency': inv.currency,
        'initial_amount': inv.initial_amount,
        'contributions': contributions,
        'returns': returns,
        'withdrawals': withdrawals,
        'fees': fees,
        'invested_capital': capital,
        'current_balance': capital + returns - withdrawals - fees,
        'net_return': returns - fees,
    }


def portfolio_summary(investments):
    """Resumen de inversiones activas agrupado por moneda."""
    result = {}
    for inv in investments.filter(status='active').prefetch_related('movements'):
        data = investment_summary(inv)
        row = result.setdefault(inv.currency, {
            'investments': 0, 'invested_capital': Decimal('0'), 'current_balance': Decimal('0'),
        })
        row['investments'] += 1
        row['invested_capital'] += data['invested_capital']
        row['current_balance'] += data['current_balance']
    return result
