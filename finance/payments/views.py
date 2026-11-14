from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from .models import FeeNotePayment, WHTCredit
from .serializers import FeeNotePaymentSerializer, WHTCreditSerializer


class FeeNotePaymentViewSet(viewsets.ModelViewSet):
    queryset = FeeNotePayment.objects.all()
    serializer_class = FeeNotePaymentSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ('tenant', 'fee_note', 'payment_currency', 'wht_deducted')
    search_fields = ('fee_note__fee_note_number', 'bank_reference')


class WHTCreditViewSet(viewsets.ModelViewSet):
    queryset = WHTCredit.objects.all()
    serializer_class = WHTCreditSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ('tenant', 'is_utilised', 'period_year')
