from rest_framework import viewsets

from finance.security.permissions import TenantScopedMixin

from .models import Account, JournalEntry, JournalLine
from .serializers import AccountSerializer, JournalEntrySerializer, JournalLineSerializer


class AccountViewSet(TenantScopedMixin, viewsets.ModelViewSet):
    queryset = Account.objects.all()
    serializer_class = AccountSerializer
    filterset_fields = ('tenant', 'category', 'is_active')
    search_fields = ('code', 'name')


class JournalEntryViewSet(TenantScopedMixin, viewsets.ModelViewSet):
    queryset = JournalEntry.objects.all()
    serializer_class = JournalEntrySerializer
    filterset_fields = ('tenant', 'is_void', 'entry_date')
    search_fields = ('reference', 'description')


class JournalLineViewSet(TenantScopedMixin, viewsets.ModelViewSet):
    queryset = JournalLine.objects.all()
    serializer_class = JournalLineSerializer
    filterset_fields = ('tenant', 'journal_entry')
