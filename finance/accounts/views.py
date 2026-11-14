from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from .models import Account, JournalEntry, JournalLine
from .serializers import AccountSerializer, JournalEntrySerializer, JournalLineSerializer


class AccountViewSet(viewsets.ModelViewSet):
    queryset = Account.objects.all()
    serializer_class = AccountSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ('tenant', 'category', 'is_active')
    search_fields = ('code', 'name')


class JournalEntryViewSet(viewsets.ModelViewSet):
    queryset = JournalEntry.objects.all()
    serializer_class = JournalEntrySerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ('tenant', 'is_void', 'entry_date')
    search_fields = ('reference', 'description')


class JournalLineViewSet(viewsets.ModelViewSet):
    queryset = JournalLine.objects.all()
    serializer_class = JournalLineSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ('tenant', 'journal_entry')
