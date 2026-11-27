from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from finance.accounts.services import AccountingConfigError
from finance.security.permissions import TenantScopedMixin
from tenants.models import Tenant

from .config import PayrollConfigError
from .models import EmployeeAllowance, EmployeePayrollProfile, PayrollLine, PayrollRun
from .serializers import (
    EmployeeAllowanceSerializer, EmployeePayrollProfileSerializer, PayrollLineSerializer, PayrollRunSerializer,
)
from .services import PayrollError, PayrollService

# Los salarios son confidenciales: analistas y lectores no los ven.
PAYROLL_READ_ROLES = ('admin', 'manager', 'auditor')


class PayrollScopedMixin(TenantScopedMixin):
    read_roles = PAYROLL_READ_ROLES


class EmployeePayrollProfileViewSet(PayrollScopedMixin, viewsets.ModelViewSet):
    queryset = EmployeePayrollProfile.objects.select_related('user')
    serializer_class = EmployeePayrollProfileSerializer
    filterset_fields = ('tenant', 'is_active')
    search_fields = ('employee_number', 'user__username')


class EmployeeAllowanceViewSet(PayrollScopedMixin, viewsets.ModelViewSet):
    tenant_path = 'employee__tenant'
    queryset = EmployeeAllowance.objects.select_related('employee')
    serializer_class = EmployeeAllowanceSerializer
    filterset_fields = ('employee', 'allowance_type', 'is_active')


class PayrollRunViewSet(PayrollScopedMixin, viewsets.ModelViewSet):
    queryset = PayrollRun.objects.all()
    serializer_class = PayrollRunSerializer
    filterset_fields = ('tenant', 'status', 'year', 'month', 'period')

    @action(detail=False, methods=['post'])
    def run_monthly(self, request):
        """Calcula la nomina. `period`: monthly (por defecto), q1 o q2 (quincenas)."""
        try:
            tenant_id = int(request.data.get('tenant_id'))
            month = int(request.data.get('month'))
            year = int(request.data.get('year'))
        except (TypeError, ValueError):
            return Response(
                {'error': 'tenant_id, month y year son obligatorios y deben ser numeros enteros.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not 1 <= month <= 12:
            return Response({'error': 'month debe estar entre 1 y 12.'}, status=status.HTTP_400_BAD_REQUEST)
        period = request.data.get('period', 'monthly')
        self.check_tenant_access(tenant_id)
        try:
            tenant = Tenant.objects.get(pk=tenant_id)
        except Tenant.DoesNotExist:
            return Response({'error': 'Empresa no encontrada.'}, status=status.HTTP_404_NOT_FOUND)
        try:
            payroll_run = PayrollService.run_payroll(tenant, month, year, request.user, period)
        except (PayrollError, PayrollConfigError) as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(PayrollRunSerializer(payroll_run).data)

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        """Aprueba la nomina y genera su asiento contable."""
        try:
            payroll_run = PayrollService.approve(self.get_object(), request.user)
        except (PayrollError, AccountingConfigError) as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(PayrollRunSerializer(payroll_run).data)


class PayrollLineViewSet(PayrollScopedMixin, viewsets.ModelViewSet):
    tenant_path = 'payroll_run__tenant'
    queryset = PayrollLine.objects.select_related('payroll_run', 'employee')
    serializer_class = PayrollLineSerializer
    filterset_fields = ('payroll_run', 'employee')
