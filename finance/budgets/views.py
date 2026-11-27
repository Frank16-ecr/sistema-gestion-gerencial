from django.utils import timezone

from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from finance.security.permissions import IsManagerOrReadOnly, TenantScopedMixin

from .models import Budget, BudgetLine
from .serializers import BudgetLineSerializer, BudgetSerializer
from .services import budget_execution


class BudgetViewSet(TenantScopedMixin, viewsets.ModelViewSet):
    queryset = Budget.objects.prefetch_related('lines')
    serializer_class = BudgetSerializer
    permission_classes = [IsManagerOrReadOnly]
    filterset_fields = ('tenant', 'fiscal_year', 'status', 'currency')
    search_fields = ('name', 'notes')

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        budget = self.get_object()
        if budget.status != 'draft':
            return Response({'detail': 'Solo se aprueban presupuestos en borrador.'}, status=400)
        budget.status = 'approved'
        budget.approved_by = request.user
        budget.approved_at = timezone.now()
        budget.save(update_fields=['status', 'approved_by', 'approved_at'])
        return Response(self.get_serializer(budget).data)

    @action(detail=True, methods=['get'])
    def execution(self, request, pk=None):
        """Presupuesto vs. gasto real (gastos aprobados o pagados en el periodo)."""
        return Response(budget_execution(self.get_object()))


class BudgetLineViewSet(TenantScopedMixin, viewsets.ModelViewSet):
    tenant_path = 'budget__tenant'
    queryset = BudgetLine.objects.select_related('budget')
    serializer_class = BudgetLineSerializer
    permission_classes = [IsManagerOrReadOnly]
    filterset_fields = ('budget', 'category')
