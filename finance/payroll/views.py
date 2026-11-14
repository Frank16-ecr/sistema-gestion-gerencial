from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from .models import EmployeePayrollProfile, EmployeeAllowance, PayrollRun, PayrollLine
from .serializers import (
    EmployeePayrollProfileSerializer, EmployeeAllowanceSerializer,
    PayrollRunSerializer, PayrollLineSerializer,
)
from .services import PayrollService


class EmployeePayrollProfileViewSet(viewsets.ModelViewSet):
    queryset = EmployeePayrollProfile.objects.all()
    serializer_class = EmployeePayrollProfileSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ('tenant', 'is_active')
    search_fields = ('employee_number', 'user__username')


class EmployeeAllowanceViewSet(viewsets.ModelViewSet):
    queryset = EmployeeAllowance.objects.all()
    serializer_class = EmployeeAllowanceSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ('employee', 'allowance_type', 'is_active')


class PayrollRunViewSet(viewsets.ModelViewSet):
    queryset = PayrollRun.objects.all()
    serializer_class = PayrollRunSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ('tenant', 'status', 'year', 'month')

    @action(detail=False, methods=['post'])
    def run_monthly(self, request):
        tenant_id = request.data.get('tenant_id')
        month = request.data.get('month')
        year = request.data.get('year')
        from tenants.models import Tenant
        try:
            tenant = Tenant.objects.get(pk=tenant_id)
        except Tenant.DoesNotExist:
            return Response({'error': 'Tenant not found'}, status=status.HTTP_404_NOT_FOUND)
        payroll_run = PayrollService.run_monthly_payroll(tenant, int(month), int(year), request.user)
        return Response(PayrollRunSerializer(payroll_run).data)


class PayrollLineViewSet(viewsets.ModelViewSet):
    queryset = PayrollLine.objects.all()
    serializer_class = PayrollLineSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ('payroll_run', 'employee')
