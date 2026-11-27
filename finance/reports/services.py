import logging
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Count, Q, Sum

logger = logging.getLogger(__name__)

ZERO = Decimal('0')

# Avisos del resumen gerencial
BUDGET_WARNING_PERCENT = Decimal('90')
UPCOMING_OBLIGATION_DAYS = 15


def _sum(value):
    return value if value is not None else ZERO


class ReportService:

    @staticmethod
    def _journal_totals(tenant, category, start_date=None, end_date=None):
        """Debitos y creditos de las cuentas activas de una categoria."""
        from finance.accounts.models import JournalLine

        lines = JournalLine.objects.filter(
            tenant=tenant,
            journal_entry__is_void=False,
            account__category=category,
            account__is_active=True,
        )
        if start_date:
            lines = lines.filter(journal_entry__entry_date__gte=start_date)
        if end_date:
            lines = lines.filter(journal_entry__entry_date__lte=end_date)
        totals = lines.aggregate(debit=Sum('debit_amount'), credit=Sum('credit_amount'))
        return _sum(totals['debit']), _sum(totals['credit'])

    @staticmethod
    def get_income_statement(tenant, start_date, end_date):
        """Generate a basic income statement for the given period."""
        income_debit, income_credit = ReportService._journal_totals(tenant, 'income', start_date, end_date)
        expense_debit, expense_credit = ReportService._journal_totals(tenant, 'expense', start_date, end_date)

        total_income = income_credit - income_debit
        total_expenses = expense_debit - expense_credit
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
    def get_balance_sheet(tenant, as_of):
        """Balance general a una fecha, con detalle por cuenta.

        El resultado acumulado (ingresos - gastos aun no cerrados contra
        patrimonio) se muestra como `current_earnings`, de modo que
        activos = pasivos + patrimonio + resultado.
        """
        from finance.accounts.models import Account

        sections = {}
        for category, sign in (('asset', 1), ('liability', -1), ('equity', -1)):
            accounts = (
                Account.objects.filter(tenant=tenant, category=category, is_active=True)
                .annotate(
                    debit=Sum('journalline__debit_amount', filter=Q(
                        journalline__journal_entry__is_void=False,
                        journalline__journal_entry__entry_date__lte=as_of,
                    )),
                    credit=Sum('journalline__credit_amount', filter=Q(
                        journalline__journal_entry__is_void=False,
                        journalline__journal_entry__entry_date__lte=as_of,
                    )),
                )
                .order_by('code')
            )
            rows, total = [], ZERO
            for acc in accounts:
                balance = (_sum(acc.debit) - _sum(acc.credit)) * sign
                if balance == 0:
                    continue
                rows.append({'code': acc.code, 'name': acc.name, 'balance': balance})
                total += balance
            sections[category] = {'accounts': rows, 'total': total}

        income_debit, income_credit = ReportService._journal_totals(tenant, 'income', end_date=as_of)
        expense_debit, expense_credit = ReportService._journal_totals(tenant, 'expense', end_date=as_of)
        current_earnings = (income_credit - income_debit) - (expense_debit - expense_credit)

        total_assets = sections['asset']['total']
        total_liabilities_equity = sections['liability']['total'] + sections['equity']['total'] + current_earnings
        return {
            'tenant': str(tenant),
            'as_of': str(as_of),
            'assets': sections['asset'],
            'liabilities': sections['liability'],
            'equity': sections['equity'],
            'current_earnings': current_earnings,
            'total_assets': total_assets,
            'total_liabilities_and_equity': total_liabilities_equity,
            'is_balanced': total_assets == total_liabilities_equity,
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

    # ------------------------------------------------------------------
    # Resumen gerencial
    # ------------------------------------------------------------------

    @staticmethod
    def _receivables(tenant, today=None):
        """Cuentas por cobrar por moneda: facturas venezolanas (sales) y notas de cobro (invoicing)."""
        from finance.invoicing.models import FeeNote
        from finance.sales.models import Invoice

        today = today or date.today()
        result = {}

        def add(currency, count, due, overdue_count, overdue_due):
            row = result.setdefault(currency, {
                'count': 0, 'balance_due': ZERO, 'overdue_count': 0, 'overdue_balance': ZERO,
            })
            row['count'] += count
            row['balance_due'] += _sum(due)
            row['overdue_count'] += overdue_count
            row['overdue_balance'] += _sum(overdue_due)

        overdue_sale = Q(due_date__lt=today)
        sales_rows = (
            Invoice.objects.filter(tenant=tenant, status__in=('issued', 'partial'), balance_due__gt=0)
            .exclude(doc_type='credit_note')
            .values('currency')
            .annotate(invoices=Count('id'), total_due=Sum('balance_due'),
                      overdue_invoices=Count('id', filter=overdue_sale),
                      overdue_due=Sum('balance_due', filter=overdue_sale))
        )
        for r in sales_rows:
            add(r['currency'], r['invoices'], r['total_due'], r['overdue_invoices'], r['overdue_due'])

        overdue_fee = Q(status__startswith='overdue')
        fee_rows = (
            FeeNote.objects.filter(tenant=tenant, is_void=False)
            .exclude(status__in=('paid', 'void'))
            .values('invoice_currency')
            .annotate(invoices=Count('id'), total_due=Sum('balance_due'),
                      overdue_invoices=Count('id', filter=overdue_fee),
                      overdue_due=Sum('balance_due', filter=overdue_fee))
        )
        for r in fee_rows:
            add(r['invoice_currency'], r['invoices'], r['total_due'], r['overdue_invoices'], r['overdue_due'])
        return dict(sorted(result.items()))

    @staticmethod
    def _expenses(tenant, start_date, end_date):
        from finance.budgets.services import SPENT_STATUSES
        from finance.expenses.models import Expense

        period = Expense.objects.filter(tenant=tenant, expense_date__range=(start_date, end_date))
        by_currency = {}
        rows = (
            period.filter(status__in=SPENT_STATUSES)
            .values('currency', 'category')
            .annotate(total=Sum('amount'))
            .order_by('currency', '-total')
        )
        for r in rows:
            entry = by_currency.setdefault(r['currency'], {'total': ZERO, 'by_category': {}})
            entry['by_category'][r['category']] = r['total']
            entry['total'] += r['total']
        pending = period.filter(status='pending').aggregate(count=Count('id'))
        return {'by_currency': by_currency, 'pending_approval': pending['count']}

    @staticmethod
    def _budgets(tenant, start_date, end_date):
        from finance.budgets.models import Budget
        from finance.budgets.services import budget_execution

        budgets = Budget.objects.filter(
            tenant=tenant, status='approved', period_start__lte=end_date, period_end__gte=start_date,
        ).prefetch_related('lines')
        return [budget_execution(b) for b in budgets]

    @staticmethod
    def _obligations(tenant, today):
        from finance.statutory.models import StatutoryObligation

        open_qs = StatutoryObligation.objects.filter(tenant=tenant).exclude(status='paid')
        overdue = open_qs.filter(due_date__lt=today)
        upcoming = open_qs.filter(due_date__gte=today, due_date__lte=today + timedelta(days=UPCOMING_OBLIGATION_DAYS))
        totals = open_qs.aggregate(count=Count('id'), amount=Sum('amount_due'))
        overdue_totals = overdue.aggregate(count=Count('id'), amount=Sum('amount_due'))
        return {
            'open_count': totals['count'],
            'open_amount': _sum(totals['amount']),
            'overdue_count': overdue_totals['count'],
            'overdue_amount': _sum(overdue_totals['amount']),
            'upcoming': list(
                upcoming.order_by('due_date').values('obligation_type', 'amount_due', 'due_date', 'status')[:10]
            ),
        }

    @staticmethod
    def _cash(tenant):
        from finance.banking.models import BankAccount

        rows = (
            BankAccount.objects.filter(tenant=tenant, is_active=True)
            .values('currency')
            .annotate(accounts=Count('id'), balance=Sum('current_balance'))
            .order_by('currency')
        )
        return {r['currency']: {'accounts': r['accounts'], 'balance': _sum(r['balance'])} for r in rows}

    @staticmethod
    def _latest_rates(tenant, base):
        from finance.fx.models import ExchangeRate

        rates = {}
        for row in ExchangeRate.objects.filter(tenant=tenant, to_currency=base).order_by('-rate_date', '-id'):
            if row.from_currency not in rates:
                rates[row.from_currency] = {'rate': row.rate, 'date': row.rate_date, 'source': row.source}
        return rates

    @staticmethod
    def _alerts(data):
        from finance.expenses.models import Expense

        labels = dict(Expense.CATEGORY_CHOICES)
        alerts = []
        for b in data['budgets']:
            pct = b['percent_used']
            if pct is not None and pct >= 100:
                alerts.append({'level': 'danger', 'message': f"Presupuesto '{b['name']}' excedido ({pct}%)."})
            elif pct is not None and pct >= BUDGET_WARNING_PERCENT:
                alerts.append({'level': 'warning', 'message': f"Presupuesto '{b['name']}' al {pct}%."})
            for line in b['lines']:
                if line['over_budget']:
                    category = labels.get(line['category'], line['category'])
                    alerts.append({
                        'level': 'warning',
                        'message': f"'{b['name']}': la categoría {category} supera lo planificado.",
                    })
        obligations = data['obligations']
        if obligations['overdue_count']:
            alerts.append({
                'level': 'danger',
                'message': f"{obligations['overdue_count']} obligación(es) fiscal(es) vencida(s) sin pagar.",
            })
        overdue_invoices = sum(r['overdue_count'] for r in data['receivables'].values())
        if overdue_invoices:
            alerts.append({'level': 'warning', 'message': f"{overdue_invoices} factura(s) vencida(s) por cobrar."})
        if data['expenses']['pending_approval']:
            alerts.append({
                'level': 'info',
                'message': f"{data['expenses']['pending_approval']} gasto(s) pendiente(s) de aprobación.",
            })
        return alerts

    @staticmethod
    def get_management_dashboard(tenant, start_date, end_date, today=None):
        """Indicadores clave de la empresa para el periodo indicado.

        Los importes se agrupan por moneda: no se suman monedas distintas.
        """
        from finance.investments.models import Investment
        from finance.investments.services import portfolio_by_currency
        from tenants.config import base_currency

        today = today or date.today()
        currency = base_currency(tenant)
        data = {
            'tenant': {'id': tenant.id, 'name': tenant.name},
            'base_currency': currency,
            'exchange_rates': ReportService._latest_rates(tenant, currency),
            'period_start': str(start_date),
            'period_end': str(end_date),
            'income_statement': ReportService.get_income_statement(tenant, start_date, end_date),
            'cash': ReportService._cash(tenant),
            'receivables': ReportService._receivables(tenant, today),
            'expenses': ReportService._expenses(tenant, start_date, end_date),
            'budgets': ReportService._budgets(tenant, start_date, end_date),
            'investments': portfolio_by_currency(Investment.objects.filter(tenant=tenant, status='active')),
            'obligations': ReportService._obligations(tenant, today),
        }
        data['alerts'] = ReportService._alerts(data)
        return data
