from rest_framework import viewsets

from finance.security.permissions import TenantScopedMixin

from .models import Expense, ReimbursementBatch, ReimbursementRequest
from .serializers import ExpenseSerializer, ReimbursementBatchSerializer, ReimbursementRequestSerializer


class ExpenseViewSet(TenantScopedMixin, viewsets.ModelViewSet):
    queryset = Expense.objects.all()
    serializer_class = ExpenseSerializer
    filterset_fields = ('tenant', 'category', 'status', 'currency')
    search_fields = ('description', 'notes')


class ReimbursementBatchViewSet(TenantScopedMixin, viewsets.ModelViewSet):
    queryset = ReimbursementBatch.objects.all()
    serializer_class = ReimbursementBatchSerializer
    filterset_fields = ('tenant', 'status')


class ReimbursementRequestViewSet(TenantScopedMixin, viewsets.ModelViewSet):
    queryset = ReimbursementRequest.objects.all()
    serializer_class = ReimbursementRequestSerializer
    filterset_fields = ('tenant', 'status', 'batch')
    search_fields = ('description',)
