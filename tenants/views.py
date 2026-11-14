from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from .models import Tenant, TenantSetting
from .serializers import TenantSerializer, TenantSettingSerializer


class TenantViewSet(viewsets.ModelViewSet):
    queryset = Tenant.objects.all()
    serializer_class = TenantSerializer
    permission_classes = [IsAuthenticated]
    search_fields = ('name', 'slug')
    filterset_fields = ('is_active',)


class TenantSettingViewSet(viewsets.ModelViewSet):
    queryset = TenantSetting.objects.all()
    serializer_class = TenantSettingSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ('tenant',)
