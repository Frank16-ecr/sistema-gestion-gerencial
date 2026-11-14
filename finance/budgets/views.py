from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from finance.expenses.models import Expense
from finance.security.permissions import IsManagerOrReadOnly, TenantScopedMixin

from .models import Budget, BudgetLine
from .serializers import BudgetLineSerializer, BudgetSerializer


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
        budget = self.get_object()
        spent_rows = (
            Expense.objects.filter(
                tenant=budget.tenant,
                currency=budget.currency,
                status__in=['approved', 'paid'],
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

        return Response({
            'budget': budget.id,
            'currency': budget.currency,
            'total_planned': total_planned,
            'total_spent': total_spent,
            'total_remaining': total_planned - total_spent,
            'lines': lines,
            'unbudgeted_spending': unbudgeted,
        })


class BudgetLineViewSet(TenantScopedMixin, viewsets.ModelViewSet):
    tenant_path = 'budget__tenant'
    queryset = BudgetLine.objects.select_related('budget')
    serializer_class = BudgetLineSerializer
    permission_classes = [IsManagerOrReadOnly]
    filterset_fields = ('budget', 'category')
