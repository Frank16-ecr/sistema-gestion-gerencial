from django.urls import path

from .views import (
    BalanceSheetView, IncomeStatementView, ManagementDashboardView, OutstandingInvoicesView, PayrollSummaryView,
)

urlpatterns = [
    path('income-statement/', IncomeStatementView.as_view(), name='income-statement'),
    path('balance-sheet/', BalanceSheetView.as_view(), name='balance-sheet'),
    path('outstanding-invoices/', OutstandingInvoicesView.as_view(), name='outstanding-invoices'),
    path('payroll-summary/', PayrollSummaryView.as_view(), name='payroll-summary'),
    path('dashboard/', ManagementDashboardView.as_view(), name='management-dashboard'),
]
