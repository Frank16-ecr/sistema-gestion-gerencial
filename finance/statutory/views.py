from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from .models import StatutoryObligation
from .serializers import StatutoryObligationSerializer


class StatutoryObligationViewSet(viewsets.ModelViewSet):
    queryset = StatutoryObligation.objects.all()
    serializer_class = StatutoryObligationSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ('tenant', 'obligation_type', 'status', 'period_year', 'period_month')
    search_fields = ('payment_reference',)
