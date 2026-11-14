from decimal import Decimal

from django.db.models import Sum
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from finance.security.permissions import IsManagerOrReadOnly, TenantScopedMixin

from .models import Investment, InvestmentMovement
from .serializers import InvestmentMovementSerializer, InvestmentSerializer


def _total(qs, movement_type):
    return qs.filter(movement_type=movement_type).aggregate(t=Sum('amount'))['t'] or Decimal('0')


class InvestmentViewSet(TenantScopedMixin, viewsets.ModelViewSet):
    queryset = Investment.objects.all()
    serializer_class = InvestmentSerializer
    permission_classes = [IsManagerOrReadOnly]
    filterset_fields = ('tenant', 'asset_type', 'status', 'currency')
    search_fields = ('name', 'institution', 'notes')

    @action(detail=True, methods=['get'])
    def summary(self, request, pk=None):
        """Capital, rendimientos acumulados y saldo actual de una inversion."""
        inv = self.get_object()
        movs = inv.movements.all()
        contributions = _total(movs, 'contribution')
        returns = _total(movs, 'return')
        withdrawals = _total(movs, 'withdrawal')
        fees = _total(movs, 'fee')
        capital = inv.initial_amount + contributions
        return Response({
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
        })

    @action(detail=False, methods=['get'])
    def portfolio(self, request):
        """Resumen del portafolio activo agrupado por moneda."""
        qs = self.filter_queryset(self.get_queryset()).filter(status='active')
        result = {}
        for inv in qs.prefetch_related('movements'):
            movs = inv.movements.all()
            contributions = sum((m.amount for m in movs if m.movement_type == 'contribution'), Decimal('0'))
            returns = sum((m.amount for m in movs if m.movement_type == 'return'), Decimal('0'))
            withdrawals = sum((m.amount for m in movs if m.movement_type == 'withdrawal'), Decimal('0'))
            fees = sum((m.amount for m in movs if m.movement_type == 'fee'), Decimal('0'))
            row = result.setdefault(inv.currency, {
                'investments': 0, 'invested_capital': Decimal('0'), 'current_balance': Decimal('0'),
            })
            capital = inv.initial_amount + contributions
            row['investments'] += 1
            row['invested_capital'] += capital
            row['current_balance'] += capital + returns - withdrawals - fees
        return Response(result)


class InvestmentMovementViewSet(TenantScopedMixin, viewsets.ModelViewSet):
    tenant_path = 'investment__tenant'
    queryset = InvestmentMovement.objects.select_related('investment')
    serializer_class = InvestmentMovementSerializer
    permission_classes = [IsManagerOrReadOnly]
    filterset_fields = ('investment', 'movement_type')
