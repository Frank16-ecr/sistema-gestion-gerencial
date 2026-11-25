from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from finance.security.permissions import TenantScopedMixin

from .models import FeeNote, FeeNoteReminder
from .serializers import FeeNoteReminderSerializer, FeeNoteSerializer
from .services import FeeNoteService


class FeeNoteViewSet(TenantScopedMixin, viewsets.ModelViewSet):
    queryset = FeeNote.objects.all()
    serializer_class = FeeNoteSerializer
    filterset_fields = ('tenant', 'status', 'is_void', 'invoice_currency')
    search_fields = ('fee_note_number', 'insurer_name', 'efris_fiscal_number')

    @action(detail=True, methods=['post'])
    def void(self, request, pk=None):
        fee_note = self.get_object()
        reason = request.data.get('reason', '')
        FeeNoteService.void_fee_note(fee_note, reason, request.user)
        return Response({'status': 'voided'})

    @action(detail=True, methods=['post'])
    def submit_to_efris(self, request, pk=None):
        fee_note = self.get_object()
        FeeNoteService.submit_to_efris(fee_note)
        return Response({'status': 'submitted'})

    @action(detail=True, methods=['post'])
    def send_to_insurer(self, request, pk=None):
        fee_note = self.get_object()
        FeeNoteService.send_to_insurer(fee_note, request.user)
        return Response({'status': 'sent'})


class FeeNoteReminderViewSet(TenantScopedMixin, viewsets.ModelViewSet):
    tenant_path = 'fee_note__tenant'
    queryset = FeeNoteReminder.objects.select_related('fee_note')
    serializer_class = FeeNoteReminderSerializer
    filterset_fields = ('fee_note', 'reminder_type', 'success')
