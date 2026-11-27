from datetime import date

from django.utils.dateparse import parse_date

from rest_framework import status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from finance.security.permissions import ALL_ROLES, has_tenant_role
from tenants.models import Tenant

from .services import ReportService

PAYROLL_REPORT_ROLES = ('admin', 'manager', 'auditor')


def _parse_date_param(params, name, default=None):
    raw = params.get(name)
    if not raw:
        if default is not None:
            return default
        raise ValidationError({name: 'Este parametro es obligatorio (AAAA-MM-DD).'})
    value = parse_date(raw)
    if value is None:
        raise ValidationError({name: 'Fecha invalida, usa el formato AAAA-MM-DD.'})
    return value


class TenantReportView(APIView):
    """Base de los reportes: resuelve la empresa y comprueba el acceso."""

    permission_classes = [IsAuthenticated]
    report_roles = ALL_ROLES

    def get_tenant(self, request):
        tenant_id = request.query_params.get('tenant_id')
        if not tenant_id:
            raise ValidationError({'tenant_id': 'Este parametro es obligatorio.'})
        try:
            tenant = Tenant.objects.get(pk=int(tenant_id))
        except (ValueError, Tenant.DoesNotExist):
            tenant = None
        # Misma respuesta si la empresa no existe o no es tuya: no se revela cuales existen.
        if tenant is None or not has_tenant_role(request.user, tenant.pk, self.report_roles):
            raise PermissionDenied('No tienes acceso a esa empresa.')
        return tenant


class IncomeStatementView(TenantReportView):

    def get(self, request):
        tenant = self.get_tenant(request)
        start_date = _parse_date_param(request.query_params, 'start_date')
        end_date = _parse_date_param(request.query_params, 'end_date')
        if end_date < start_date:
            return Response({'error': 'end_date no puede ser anterior a start_date.'},
                            status=status.HTTP_400_BAD_REQUEST)
        return Response(ReportService.get_income_statement(tenant, start_date, end_date))


class BalanceSheetView(TenantReportView):

    def get(self, request):
        tenant = self.get_tenant(request)
        as_of = _parse_date_param(request.query_params, 'as_of', default=date.today())
        return Response(ReportService.get_balance_sheet(tenant, as_of))


class OutstandingInvoicesView(TenantReportView):

    def get(self, request):
        tenant = self.get_tenant(request)
        return Response(ReportService.get_outstanding_invoices(tenant))


class PayrollSummaryView(TenantReportView):
    report_roles = PAYROLL_REPORT_ROLES

    def get(self, request):
        tenant = self.get_tenant(request)
        try:
            year = int(request.query_params.get('year'))
        except (TypeError, ValueError):
            return Response({'error': 'year es obligatorio y debe ser un numero.'},
                            status=status.HTTP_400_BAD_REQUEST)
        return Response(ReportService.get_payroll_summary(tenant, year))


def dashboard_period(params):
    """Periodo del resumen: por defecto, del 1 de enero de este anio a hoy."""
    today = date.today()
    start_date = _parse_date_param(params, 'start_date', default=date(today.year, 1, 1))
    end_date = _parse_date_param(params, 'end_date', default=today)
    if end_date < start_date:
        raise ValidationError({'end_date': 'No puede ser anterior a start_date.'})
    return start_date, end_date


class ManagementDashboardView(TenantReportView):
    """Resumen gerencial: caja, cobros, gastos, presupuestos, inversiones,
    obligaciones y alertas de una empresa."""

    def get(self, request):
        tenant = self.get_tenant(request)
        start_date, end_date = dashboard_period(request.query_params)
        return Response(ReportService.get_management_dashboard(tenant, start_date, end_date))
