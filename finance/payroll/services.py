import calendar
import logging
from datetime import date, timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from .config import DEFAULT_PAYROLL_CONFIG, contribution_base, get_payroll_config

logger = logging.getLogger(__name__)


class PayrollService:

    @staticmethod
    def calculate_income_tax(taxable_income, bands):
        """Impuesto progresivo por tramos [[limite_superior, tasa_%], ...]."""
        income = Decimal(str(taxable_income))
        tax = Decimal('0')
        lower = Decimal('0')
        for limit, rate in bands:
            upper = None if limit is None else Decimal(str(limit))
            if income <= lower:
                break
            taxable_in_band = (income if upper is None else min(income, upper)) - lower
            tax += taxable_in_band * Decimal(str(rate)) / Decimal('100')
            if upper is None:
                break
            lower = upper
        return tax.quantize(Decimal('0.01'))

    @staticmethod
    def calculate_paye(taxable_income, bands=None):
        """
        Impuesto sobre la renta mensual. Sin `bands` usa los tramos de Uganda
        (PAYE, montos mensuales en UGX):
        - 0 - 235,000: 0%
        - 235,001 - 335,000: 10%
        - 335,001 - 410,000: 20%
        - 410,001 - 10,000,000: 30%
        - Above 10,000,000: 40%
        """
        if bands is None:
            bands = DEFAULT_PAYROLL_CONFIG['income_tax']['bands']
        return PayrollService.calculate_income_tax(taxable_income, bands)

    @staticmethod
    def calculate_nssf(gross_salary, social_security=None):
        """
        Aportes a la seguridad social (empleado, empleador). Sin parametros usa
        NSSF de Uganda: empleado 5% y empleador 10% del salario bruto.
        """
        social = social_security or DEFAULT_PAYROLL_CONFIG['social_security']
        gross = Decimal(str(gross_salary))
        cap = social.get('monthly_cap')
        if cap is not None:
            gross = min(gross, Decimal(str(cap)))
        employee_rate = Decimal(str(social.get('employee_rate', 0))) / Decimal('100')
        employer_rate = Decimal(str(social.get('employer_rate', 0))) / Decimal('100')
        employee_contribution = (gross * employee_rate).quantize(Decimal('0.01'))
        employer_contribution = (gross * employer_rate).quantize(Decimal('0.01'))
        return employee_contribution, employer_contribution

    @staticmethod
    def calculate_employee_income_tax(employee, taxable_income, income_tax, factor=Decimal('1')):
        """Retencion del impuesto sobre la renta de un trabajador en el periodo.

        `taxable_income` es la renta del periodo. Con tramos (mensuales) se calcula
        el impuesto del mes y se prorratea con `factor` (1/2 en una quincena).
        """
        if income_tax.get('method') == 'employee_rate':
            rate = employee.income_tax_rate or Decimal('0')
            return (Decimal(str(taxable_income)) * rate / HUNDRED).quantize(CENT)
        monthly_income = Decimal(str(taxable_income)) / factor
        monthly_tax = PayrollService.calculate_income_tax(monthly_income, income_tax['bands'])
        return (monthly_tax * factor).quantize(CENT)

    @staticmethod
    def calculate_contributions(salary, total, contributions, minimum_wage=None, factor=Decimal('1'),
                                mondays=None):
        """Aportes de trabajador y patrono por codigo: {code: {base, employee, employer}}.

        `salary` y `total` son montos MENSUALES (los topes son mensuales).
        - Aporte semanal (`weekly`, p. ej. IVSS y RPE): base semanal = base mensual x 12 / 52,
          multiplicada por los lunes del periodo (`mondays`).
        - Resto: aporte mensual x `factor` (1 en nomina mensual, 1/2 en quincena).
        """
        result = {}
        for c in contributions:
            monthly_base = contribution_base(c, salary, total, minimum_wage)
            if c.get('weekly') and mondays is not None:
                base = monthly_base * 12 / 52 * mondays
            else:
                base = monthly_base * factor
            result[c['code']] = {
                'base': base.quantize(CENT),
                'employee': (base * Decimal(str(c['employee_rate'])) / HUNDRED).quantize(CENT),
                'employer': (base * Decimal(str(c['employer_rate'])) / HUNDRED).quantize(CENT),
            }
        return result

    @staticmethod
    def run_monthly_payroll(tenant, month, year, user, period='monthly'):
        """Compatibilidad: calcula la nomina del periodo indicado."""
        return PayrollService.run_payroll(tenant, month, year, user, period)

    @staticmethod
    @transaction.atomic
    def run_payroll(tenant, month, year, user, period='monthly'):
        """Calcula (o recalcula, si sigue en borrador) la nomina de un periodo.

        `period`: 'monthly' (mes completo), 'q1' (dias 1-15) o 'q2' (dia 16 a fin de mes).
        Genera una linea por trabajador activo y actualiza las obligaciones del mes,
        que suman todas las nominas del mes (ambas quincenas).
        """
        from finance.payroll.models import EmployeePayrollProfile, PayrollLine, PayrollRun

        if period not in PERIODS:
            raise PayrollError(f'Periodo invalido: {period}. Usa monthly, q1 o q2.')
        others = PayrollRun.objects.filter(tenant=tenant, month=month, year=year).exclude(period=period)
        if period == 'monthly' and others.exists():
            raise PayrollError('Ese mes ya se procesa por quincenas.')
        if period != 'monthly' and others.filter(period='monthly').exists():
            raise PayrollError('Ese mes ya tiene una nomina mensual.')

        payroll_run, created = PayrollRun.objects.get_or_create(
            tenant=tenant, month=month, year=year, period=period,
            defaults={'status': 'draft', 'created_by': user},
        )
        if not created and payroll_run.status != 'draft':
            logger.warning("Payroll run %s/%s %s already exists and is not in draft state.", month, year, period)
            return payroll_run

        config = get_payroll_config(tenant)
        income_tax = config['income_tax']
        contributions = config['contributions']
        minimum_wage = config.get('minimum_wage')
        start, end = period_dates(year, month, period)
        factor = Decimal('1') if period == 'monthly' else Decimal('0.5')
        mondays = count_mondays(start, end)

        employees = (
            EmployeePayrollProfile.objects.filter(tenant=tenant, is_active=True, start_date__lte=end)
            .exclude(end_date__lt=start)
            .prefetch_related('allowances')
        )
        totals = dict.fromkeys(('gross', 'tax', 'employee', 'employer', 'net'), Decimal('0'))
        by_code = {}
        PayrollLine.objects.filter(payroll_run=payroll_run).delete()

        for employee in employees:
            active_allowances = [a for a in employee.allowances.all() if a.is_active]
            monthly_salary = employee.gross_salary
            monthly_allowances = sum((a.amount for a in active_allowances), Decimal('0'))
            monthly_taxable_allowances = sum((a.amount for a in active_allowances if a.is_taxable), Decimal('0'))

            gross_salary = (monthly_salary * factor).quantize(CENT)
            total_allowances = (monthly_allowances * factor).quantize(CENT)
            taxable_income = ((monthly_salary + monthly_taxable_allowances) * factor).quantize(CENT)

            tax = PayrollService.calculate_employee_income_tax(employee, taxable_income, income_tax, factor)
            detail = PayrollService.calculate_contributions(
                monthly_salary, monthly_salary + monthly_allowances, contributions, minimum_wage,
                factor=factor, mondays=mondays,
            )
            employee_part = sum((d['employee'] for d in detail.values()), Decimal('0'))
            employer_part = sum((d['employer'] for d in detail.values()), Decimal('0'))
            net_pay = gross_salary + total_allowances - tax - employee_part

            PayrollLine.objects.create(
                payroll_run=payroll_run, employee=employee, gross_salary=gross_salary,
                total_allowances=total_allowances, taxable_income=taxable_income, paye=tax,
                nssf_employee=employee_part, nssf_employer=employer_part, net_pay=net_pay,
                contributions={code: _json_amounts(d) for code, d in detail.items()},
            )
            totals['gross'] += gross_salary + total_allowances
            totals['tax'] += tax
            totals['employee'] += employee_part
            totals['employer'] += employer_part
            totals['net'] += net_pay
            for code, d in detail.items():
                row = by_code.setdefault(code, {'employee': Decimal('0'), 'employer': Decimal('0')})
                row['employee'] += d['employee']
                row['employer'] += d['employer']

        payroll_run.period_start, payroll_run.period_end, payroll_run.mondays = start, end, mondays
        payroll_run.total_gross = totals['gross']
        payroll_run.total_paye = totals['tax']
        payroll_run.total_nssf_employee = totals['employee']
        payroll_run.total_nssf_employer = totals['employer']
        payroll_run.total_net = totals['net']
        payroll_run.contributions_summary = {code: _json_amounts(row) for code, row in by_code.items()}
        payroll_run.save()

        refresh_payroll_obligations(tenant, month, year, config)
        logger.info(
            "Payroll run %s %s/%s %s complete. Gross: %s, Tax: %s, Net: %s",
            tenant, month, year, period, totals['gross'], totals['tax'], totals['net'],
        )
        return payroll_run

    @staticmethod
    @transaction.atomic
    def approve(payroll_run, user):
        """Aprueba la nomina y registra su asiento contable."""
        from finance.accounts.services import post_entry

        if payroll_run.status != 'draft':
            raise PayrollError('Solo se aprueban nominas en borrador.')
        employer = payroll_run.total_nssf_employer
        withheld = payroll_run.total_nssf_employee
        payroll_run.journal_entry = post_entry(
            payroll_run.tenant, payroll_run.period_end or date(payroll_run.year, payroll_run.month, 1),
            [
                {'role': 'salaries_expense', 'debit': payroll_run.total_gross},
                {'role': 'employer_contributions_expense', 'debit': employer},
                {'role': 'salaries_payable', 'credit': payroll_run.total_net},
                {'role': 'income_tax_withheld_payable', 'credit': payroll_run.total_paye},
                {'role': 'payroll_contributions_payable', 'credit': withheld + employer},
            ],
            reference=f'Nomina {payroll_run}', description=f'Nomina {payroll_run}', user=user,
        )
        payroll_run.status = 'approved'
        payroll_run.approved_by = user
        payroll_run.approved_at = timezone.now()
        payroll_run.save()
        return payroll_run


HUNDRED = Decimal('100')
CENT = Decimal('0.01')
PERIODS = ('monthly', 'q1', 'q2')


class PayrollError(ValueError):
    """Operacion de nomina no permitida."""


def period_dates(year, month, period):
    last_day = calendar.monthrange(year, month)[1]
    if period == 'q1':
        return date(year, month, 1), date(year, month, 15)
    if period == 'q2':
        return date(year, month, 16), date(year, month, last_day)
    return date(year, month, 1), date(year, month, last_day)


def count_mondays(start, end):
    """Lunes entre dos fechas (incluidas): base de la cotizacion semanal del IVSS y RPE."""
    first_monday = start + timedelta(days=(7 - start.weekday()) % 7)
    if first_monday > end:
        return 0
    return (end - first_monday).days // 7 + 1


def refresh_payroll_obligations(tenant, month, year, config):
    """Obligaciones del mes = suma de todas sus nominas (mensual o ambas quincenas)."""
    from finance.payroll.models import PayrollRun
    from finance.statutory.models import StatutoryObligation

    runs = PayrollRun.objects.filter(tenant=tenant, month=month, year=year)
    tax_total = runs.aggregate(t=Sum('total_paye'))['t'] or Decimal('0')
    by_code = {}
    for run in runs:
        for code, row in (run.contributions_summary or {}).items():
            by_code[code] = by_code.get(code, Decimal('0')) + Decimal(row['employee']) + Decimal(row['employer'])

    obligations = [(config['income_tax']['code'], tax_total, config['due_day'])]
    for c in config['contributions']:
        obligations.append((c['code'], by_code.get(c['code'], Decimal('0')), c.get('due_day') or config['due_day']))

    for code, amount, due_day in obligations:
        existing = StatutoryObligation.objects.filter(
            tenant=tenant, obligation_type=code, period_month=month, period_year=year).first()
        if existing and existing.status in ('filed', 'paid'):
            continue
        if amount <= 0:
            if existing:
                existing.delete()
            continue
        StatutoryObligation.objects.update_or_create(
            tenant=tenant, obligation_type=code, period_month=month, period_year=year,
            defaults={'amount_due': amount, 'due_date': _next_month_day(month, year, due_day), 'status': 'pending'},
        )


def _json_amounts(row):
    """Importes como texto para guardarlos en JSON sin perder precision."""
    return {k: str(v) for k, v in row.items()}


def _next_month_day(month, year, day):
    """Dia `day` del mes siguiente al periodo (ajustado al ultimo dia del mes)."""
    due_month = month + 1 if month < 12 else 1
    due_year = year if month < 12 else year + 1
    last_day = calendar.monthrange(due_year, due_month)[1]
    return date(due_year, due_month, min(int(day), last_day))
