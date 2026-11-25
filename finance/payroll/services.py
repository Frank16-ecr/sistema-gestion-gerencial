import calendar
import logging
from datetime import date
from decimal import Decimal

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
    def calculate_employee_income_tax(employee, taxable_income, income_tax):
        """Retencion del impuesto sobre la renta de un trabajador."""
        if income_tax.get('method') == 'employee_rate':
            rate = employee.income_tax_rate or Decimal('0')
            return (Decimal(str(taxable_income)) * rate / Decimal('100')).quantize(Decimal('0.01'))
        return PayrollService.calculate_income_tax(taxable_income, income_tax['bands'])

    @staticmethod
    def calculate_contributions(salary, total, contributions, minimum_wage=None):
        """Aportes de trabajador y patrono por codigo: {code: {base, employee, employer}}."""
        result = {}
        for c in contributions:
            base = contribution_base(c, salary, total, minimum_wage)
            result[c['code']] = {
                'base': base,
                'employee': (base * Decimal(str(c['employee_rate'])) / Decimal('100')).quantize(Decimal('0.01')),
                'employer': (base * Decimal(str(c['employer_rate'])) / Decimal('100')).quantize(Decimal('0.01')),
            }
        return result

    @staticmethod
    def run_monthly_payroll(tenant, month, year, user):
        """
        Carga los trabajadores activos, calcula el impuesto y los aportes segun la
        configuracion de la empresa, guarda la nomina y sus lineas y genera las
        obligaciones (una por impuesto y por cada aporte).
        """
        from finance.payroll.models import EmployeePayrollProfile, PayrollLine, PayrollRun
        from finance.statutory.models import StatutoryObligation

        payroll_run, created = PayrollRun.objects.get_or_create(
            tenant=tenant,
            month=month,
            year=year,
            defaults={'status': 'draft', 'created_by': user},
        )

        if not created and payroll_run.status != 'draft':
            logger.warning("Payroll run for %s/%s already exists and is not in draft state.", month, year)
            return payroll_run

        config = get_payroll_config(tenant)
        income_tax = config['income_tax']
        contributions = config['contributions']
        minimum_wage = config.get('minimum_wage')

        employees = EmployeePayrollProfile.objects.filter(tenant=tenant, is_active=True).prefetch_related('allowances')

        totals = dict.fromkeys(('gross', 'tax', 'employee', 'employer', 'net'), Decimal('0'))
        by_code = {}

        PayrollLine.objects.filter(payroll_run=payroll_run).delete()

        for employee in employees:
            gross_salary = employee.gross_salary
            active_allowances = [a for a in employee.allowances.all() if a.is_active]
            total_allowances = sum((a.amount for a in active_allowances), Decimal('0'))
            taxable_allowances = sum((a.amount for a in active_allowances if a.is_taxable), Decimal('0'))
            taxable_income = gross_salary + taxable_allowances

            tax = PayrollService.calculate_employee_income_tax(employee, taxable_income, income_tax)
            detail = PayrollService.calculate_contributions(
                gross_salary, gross_salary + total_allowances, contributions, minimum_wage,
            )
            employee_part = sum((d['employee'] for d in detail.values()), Decimal('0'))
            employer_part = sum((d['employer'] for d in detail.values()), Decimal('0'))
            net_pay = gross_salary + total_allowances - tax - employee_part

            PayrollLine.objects.create(
                payroll_run=payroll_run,
                employee=employee,
                gross_salary=gross_salary,
                total_allowances=total_allowances,
                taxable_income=taxable_income,
                paye=tax,
                nssf_employee=employee_part,
                nssf_employer=employer_part,
                net_pay=net_pay,
                contributions={code: _json_amounts(d) for code, d in detail.items()},
            )

            totals['gross'] += gross_salary
            totals['tax'] += tax
            totals['employee'] += employee_part
            totals['employer'] += employer_part
            totals['net'] += net_pay
            for code, d in detail.items():
                row = by_code.setdefault(code, {'employee': Decimal('0'), 'employer': Decimal('0')})
                row['employee'] += d['employee']
                row['employer'] += d['employer']

        payroll_run.total_gross = totals['gross']
        payroll_run.total_paye = totals['tax']
        payroll_run.total_nssf_employee = totals['employee']
        payroll_run.total_nssf_employer = totals['employer']
        payroll_run.total_net = totals['net']
        payroll_run.contributions_summary = {code: _json_amounts(row) for code, row in by_code.items()}
        payroll_run.save()

        # Obligaciones: impuesto retenido y un aporte por cada codigo (trabajador + patrono).
        obligations = [(income_tax['code'], totals['tax'], config['due_day'])]
        for c in contributions:
            row = by_code.get(c['code'], {'employee': Decimal('0'), 'employer': Decimal('0')})
            obligations.append((c['code'], row['employee'] + row['employer'], c.get('due_day') or config['due_day']))

        for code, amount, due_day in obligations:
            if amount <= 0:
                continue
            StatutoryObligation.objects.update_or_create(
                tenant=tenant,
                obligation_type=code,
                period_month=month,
                period_year=year,
                defaults={
                    'amount_due': amount,
                    'due_date': _next_month_day(month, year, due_day),
                    'status': 'pending',
                },
            )

        logger.info(
            "Payroll run for %s/%s/%s complete. Gross: %s, Tax: %s, Net: %s",
            tenant, month, year, totals['gross'], totals['tax'], totals['net'],
        )
        return payroll_run


def _json_amounts(row):
    """Importes como texto para guardarlos en JSON sin perder precision."""
    return {k: str(v) for k, v in row.items()}


def _next_month_day(month, year, day):
    """Dia `day` del mes siguiente al periodo (ajustado al ultimo dia del mes)."""
    due_month = month + 1 if month < 12 else 1
    due_year = year if month < 12 else year + 1
    last_day = calendar.monthrange(due_year, due_month)[1]
    return date(due_year, due_month, min(int(day), last_day))
