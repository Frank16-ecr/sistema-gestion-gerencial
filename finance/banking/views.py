from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from .models import BankAccount, BankReconciliation, PettyCashTransaction, Cheque
from .serializers import BankAccountSerializer, BankReconciliationSerializer, PettyCashTransactionSerializer, ChequeSerializer


class BankAccountViewSet(viewsets.ModelViewSet):
    queryset = BankAccount.objects.all()
    serializer_class = BankAccountSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ('tenant', 'account_type', 'currency', 'is_active')
    search_fields = ('account_name', 'bank_name', 'account_number')


class BankReconciliationViewSet(viewsets.ModelViewSet):
    queryset = BankReconciliation.objects.all()
    serializer_class = BankReconciliationSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ('tenant', 'bank_account', 'status', 'period_year')


class PettyCashTransactionViewSet(viewsets.ModelViewSet):
    queryset = PettyCashTransaction.objects.all()
    serializer_class = PettyCashTransactionSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ('tenant', 'bank_account', 'transaction_type')
    search_fields = ('description', 'reference')


class ChequeViewSet(viewsets.ModelViewSet):
    queryset = Cheque.objects.all()
    serializer_class = ChequeSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ('tenant', 'bank_account', 'cheque_type', 'status')
    search_fields = ('cheque_number', 'payee_payer')
