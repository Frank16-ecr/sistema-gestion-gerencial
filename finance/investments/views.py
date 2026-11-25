from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from finance.security.permissions import IsManagerOrReadOnly, TenantScopedMixin

from .models import Investment, InvestmentMovement
from .serializers import InvestmentMovementSerializer, InvestmentSerializer
from .services import investment_summary, portfolio_by_currency


class InvestmentViewSet(TenantScopedMixin, viewsets.ModelViewSet):
    queryset = Investment.objects.all()
    serializer_class = InvestmentSerializer
    permission_classes = [IsManagerOrReadOnly]
    filterset_fields = ('tenant', 'asset_type', 'status', 'currency')
    search_fields = ('name', 'institution', 'notes')

    @action(detail=True, methods=['get'])
    def summary(self, request, pk=None):
        """Capital, rendimientos acumulados y saldo actual de una inversion."""
        return Response(investment_summary(self.get_object()))

    @action(detail=False, methods=['get'])
    def portfolio(self, request):
        """Resumen del portafolio activo agrupado por moneda."""
        qs = self.filter_queryset(self.get_queryset()).filter(status='active')
        return Response(portfolio_by_currency(qs))


class InvestmentMovementViewSet(TenantScopedMixin, viewsets.ModelViewSet):
    tenant_path = 'investment__tenant'
    queryset = InvestmentMovement.objects.select_related('investment')
    serializer_class = InvestmentMovementSerializer
    permission_classes = [IsManagerOrReadOnly]
    filterset_fields = ('investment', 'movement_type')
