from rest_framework import viewsets

from finance.security.permissions import TenantScopedMixin

from .models import FeeNotePayment, WHTCredit
from .serializers import FeeNotePaymentSerializer, WHTCreditSerializer


class FeeNotePaymentViewSet(TenantScopedMixin, viewsets.ModelViewSet):
    queryset = FeeNotePayment.objects.all()
    serializer_class = FeeNotePaymentSerializer
    filterset_fields = ('tenant', 'fee_note', 'payment_currency', 'wht_deducted')
    search_fields = ('fee_note__fee_note_number', 'bank_reference')


class WHTCreditViewSet(TenantScopedMixin, viewsets.ModelViewSet):
    queryset = WHTCredit.objects.all()
    serializer_class = WHTCreditSerializer
    filterset_fields = ('tenant', 'is_utilised', 'period_year')
