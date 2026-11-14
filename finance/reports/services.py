import logging
from decimal import Decimal
from django.db.models import Sum, Q
from django.utils import timezone

logger = logging.getLogger(__name__)


class ReportService:

    @staticmethod
    def get_income_statement(tenant, start_date, end_date):
        """Generate a basic income statement for the given period."""
        from finance.accounts.models import JournalLine, Account

        income_accounts = Account.objects.filter(tenant=tenant, category='income', is_active=True)
        expense_accounts = Account.objects.filter(tenant=tenant, category='expense', is_active=True)

        income_lines = JournalLine.objects.filter(
            tenant=tenant,
            journal_entry__entry_date__gte=start_date,
            journal_entry__entry_date__lte=end_date,
            journal_entry__is_void=False,
            account__in=income_accounts,
        ).aggregate(
            total_credit=Sum('credit_amount'),
            total_debit=Sum('debit_amount'),
        )

        expense_lines = JournalLine.objects.filter(
            tenant=tenant,
            journal_entry__entry_date__gte=start_date,
            journal_entry__entry_date__lte=end_date,
            journal_entry__is_void=False,
            account__in=expense_accounts,
        ).aggregate(
            total_debit=Sum('debit_amount'),
            total_credit=Sum('credit_amount'),
        )

        total_income = (income_lines['total_credit'] or Decimal('0')) - (income_lines['total_debit'] or Decimal('0'))
        total_expenses = (expense_lines['total_debit'] or Decimal('0')) - (expense_lines['total_credit'] or Decimal('0'))
        net_profit = total_income - total_expenses

        return {
            'tenant': str(tenant),
            'period_start': str(start_date),
            'period_end': str(end_date),
            'total_income': total_income,
            'total_expenses': total_expenses,
            'net_profit': net_profit,
        }

    @staticmethod
    def get_outstanding_invoices(tenant):
        """Get all outstanding fee notes for the tenant."""
        from finance.invoicing.models import FeeNote
        outstanding = FeeNote.objects.filter(
            tenant=tenant,
            is_void=False,
        ).exclude(status='paid').values(
            'fee_note_number', 'insurer_name', 'invoice_currency',
            'total_amount', 'amount_paid', 'balance_due', 'status', 'due_date',
        )
        return list(outstanding)

    @staticmethod
    def get_payroll_summary(tenant, year):
        """Get payroll summary for the year."""
        from finance.payroll.models import PayrollRun
        runs = PayrollRun.objects.filter(tenant=tenant, year=year).values(
            'month', 'year', 'status', 'total_gross', 'total_paye',
            'total_nssf_employee', 'total_nssf_employer', 'total_net',
        ).order_by('month')
        return list(runs)
