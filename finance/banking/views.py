from rest_framework import viewsets

from finance.security.permissions import TenantScopedMixin

from .models import BankAccount, BankReconciliation, Cheque, PettyCashTransaction
from .serializers import (
    BankAccountSerializer, BankReconciliationSerializer, ChequeSerializer, PettyCashTransactionSerializer,
)


class BankAccountViewSet(TenantScopedMixin, viewsets.ModelViewSet):
    queryset = BankAccount.objects.all()
    serializer_class = BankAccountSerializer
    filterset_fields = ('tenant', 'account_type', 'currency', 'is_active')
    search_fields = ('account_name', 'bank_name', 'account_number')


class BankReconciliationViewSet(TenantScopedMixin, viewsets.ModelViewSet):
    queryset = BankReconciliation.objects.all()
    serializer_class = BankReconciliationSerializer
    filterset_fields = ('tenant', 'bank_account', 'status', 'period_year')


class PettyCashTransactionViewSet(TenantScopedMixin, viewsets.ModelViewSet):
    queryset = PettyCashTransaction.objects.all()
    serializer_class = PettyCashTransactionSerializer
    filterset_fields = ('tenant', 'bank_account', 'transaction_type')
    search_fields = ('description', 'reference')


class ChequeViewSet(TenantScopedMixin, viewsets.ModelViewSet):
    queryset = Cheque.objects.all()
    serializer_class = ChequeSerializer
    filterset_fields = ('tenant', 'bank_account', 'cheque_type', 'status')
    search_fields = ('cheque_number', 'payee_payer')
