from rest_framework import viewsets

from finance.security.permissions import TenantScopedMixin

from .models import StatutoryObligation
from .serializers import StatutoryObligationSerializer


class StatutoryObligationViewSet(TenantScopedMixin, viewsets.ModelViewSet):
    queryset = StatutoryObligation.objects.all()
    serializer_class = StatutoryObligationSerializer
    filterset_fields = ('tenant', 'obligation_type', 'status', 'period_year', 'period_month')
    search_fields = ('payment_reference',)
