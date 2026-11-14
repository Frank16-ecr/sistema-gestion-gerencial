from django.urls import path
from .views import IncomeStatementView, OutstandingInvoicesView, PayrollSummaryView

urlpatterns = [
    path('income-statement/', IncomeStatementView.as_view(), name='income-statement'),
    path('outstanding-invoices/', OutstandingInvoicesView.as_view(), name='outstanding-invoices'),
    path('payroll-summary/', PayrollSummaryView.as_view(), name='payroll-summary'),
]
