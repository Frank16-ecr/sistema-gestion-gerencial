from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from .models import ExchangeRate
from .serializers import ExchangeRateSerializer


class ExchangeRateViewSet(viewsets.ModelViewSet):
    queryset = ExchangeRate.objects.all()
    serializer_class = ExchangeRateSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ('tenant', 'from_currency', 'to_currency', 'source')
    search_fields = ('from_currency', 'to_currency')
