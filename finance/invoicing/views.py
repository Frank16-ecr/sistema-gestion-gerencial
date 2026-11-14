from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from .models import FeeNote, FeeNoteReminder
from .serializers import FeeNoteSerializer, FeeNoteReminderSerializer
from .services import FeeNoteService


class FeeNoteViewSet(viewsets.ModelViewSet):
    queryset = FeeNote.objects.all()
    serializer_class = FeeNoteSerializer
    permission_classes = [IsAuthenticated]
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


class FeeNoteReminderViewSet(viewsets.ModelViewSet):
    queryset = FeeNoteReminder.objects.all()
    serializer_class = FeeNoteReminderSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ('fee_note', 'reminder_type', 'success')
