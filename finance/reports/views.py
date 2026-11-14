from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from .services import ReportService
from tenants.models import Tenant


class IncomeStatementView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        tenant_id = request.query_params.get('tenant_id')
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        if not all([tenant_id, start_date, end_date]):
            return Response({'error': 'tenant_id, start_date, and end_date are required'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            tenant = Tenant.objects.get(pk=tenant_id)
        except Tenant.DoesNotExist:
            return Response({'error': 'Tenant not found'}, status=status.HTTP_404_NOT_FOUND)
        data = ReportService.get_income_statement(tenant, start_date, end_date)
        return Response(data)


class OutstandingInvoicesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        tenant_id = request.query_params.get('tenant_id')
        if not tenant_id:
            return Response({'error': 'tenant_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            tenant = Tenant.objects.get(pk=tenant_id)
        except Tenant.DoesNotExist:
            return Response({'error': 'Tenant not found'}, status=status.HTTP_404_NOT_FOUND)
        data = ReportService.get_outstanding_invoices(tenant)
        return Response(data)


class PayrollSummaryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        tenant_id = request.query_params.get('tenant_id')
        year = request.query_params.get('year')
        if not all([tenant_id, year]):
            return Response({'error': 'tenant_id and year are required'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            tenant = Tenant.objects.get(pk=tenant_id)
        except Tenant.DoesNotExist:
            return Response({'error': 'Tenant not found'}, status=status.HTTP_404_NOT_FOUND)
        data = ReportService.get_payroll_summary(tenant, int(year))
        return Response(data)
