from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from .models import Expense, ReimbursementRequest, ReimbursementBatch
from .serializers import ExpenseSerializer, ReimbursementRequestSerializer, ReimbursementBatchSerializer


class ExpenseViewSet(viewsets.ModelViewSet):
    queryset = Expense.objects.all()
    serializer_class = ExpenseSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ('tenant', 'category', 'status', 'currency')
    search_fields = ('description', 'notes')


class ReimbursementBatchViewSet(viewsets.ModelViewSet):
    queryset = ReimbursementBatch.objects.all()
    serializer_class = ReimbursementBatchSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ('tenant', 'status')


class ReimbursementRequestViewSet(viewsets.ModelViewSet):
    queryset = ReimbursementRequest.objects.all()
    serializer_class = ReimbursementRequestSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ('tenant', 'status', 'batch')
    search_fields = ('description',)
