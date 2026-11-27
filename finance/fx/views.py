from rest_framework import viewsets

from finance.security.permissions import TenantScopedMixin

from .models import ExchangeRate
from .serializers import ExchangeRateSerializer


class ExchangeRateViewSet(TenantScopedMixin, viewsets.ModelViewSet):
    queryset = ExchangeRate.objects.all()
    serializer_class = ExchangeRateSerializer
    filterset_fields = ('tenant', 'from_currency', 'to_currency', 'source')
    search_fields = ('from_currency', 'to_currency')
