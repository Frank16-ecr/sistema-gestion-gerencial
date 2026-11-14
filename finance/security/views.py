from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response

from .models import UserTenantRole
from .serializers import UserTenantRoleSerializer


class UserTenantRoleViewSet(viewsets.ModelViewSet):
    """Gestión de roles. Solo personal administrador puede modificar."""

    queryset = UserTenantRole.objects.select_related('tenant', 'user')
    serializer_class = UserTenantRoleSerializer
    permission_classes = [IsAdminUser]
    filterset_fields = ('tenant', 'user', 'role', 'is_active')

    def perform_create(self, serializer):
        serializer.save(assigned_by=self.request.user)

    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def mine(self, request):
        """Roles del usuario autenticado."""
        qs = self.get_queryset().filter(user=request.user, is_active=True)
        return Response(self.get_serializer(qs, many=True).data)
