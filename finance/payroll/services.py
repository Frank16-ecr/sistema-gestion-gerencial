import logging
from decimal import Decimal

from .config import DEFAULT_PAYROLL_CONFIG, get_payroll_config

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
    def run_monthly_payroll(tenant, month, year, user):
        """
        Loads active employees, calculates PAYE/NSSF,
        saves payroll run + lines, creates statutory obligations.
        """
        import calendar
        from datetime import date

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
        tax_bands = config['income_tax']['bands']
        social_security = config['social_security']

        employees = EmployeePayrollProfile.objects.filter(tenant=tenant, is_active=True)

        total_gross = Decimal('0')
        total_paye = Decimal('0')
        total_nssf_employee = Decimal('0')
        total_nssf_employer = Decimal('0')
        total_net = Decimal('0')

        PayrollLine.objects.filter(payroll_run=payroll_run).delete()

        for employee in employees:
            gross_salary = employee.gross_salary
            active_allowances = employee.allowances.filter(is_active=True)
            total_allowances = sum((a.amount for a in active_allowances), Decimal('0'))
            taxable_allowances = sum((a.amount for a in active_allowances if a.is_taxable), Decimal('0'))
            taxable_income = gross_salary + taxable_allowances

            paye = PayrollService.calculate_paye(taxable_income, tax_bands)
            nssf_employee, nssf_employer = PayrollService.calculate_nssf(gross_salary, social_security)
            net_pay = gross_salary + total_allowances - paye - nssf_employee

            PayrollLine.objects.create(
                payroll_run=payroll_run,
                employee=employee,
                gross_salary=gross_salary,
                total_allowances=total_allowances,
                taxable_income=taxable_income,
                paye=paye,
                nssf_employee=nssf_employee,
                nssf_employer=nssf_employer,
                net_pay=net_pay,
            )

            total_gross += gross_salary
            total_paye += paye
            total_nssf_employee += nssf_employee
            total_nssf_employer += nssf_employer
            total_net += net_pay

        payroll_run.total_gross = total_gross
        payroll_run.total_paye = total_paye
        payroll_run.total_nssf_employee = total_nssf_employee
        payroll_run.total_nssf_employer = total_nssf_employer
        payroll_run.total_net = total_net
        payroll_run.save()

        # Vencimiento: dia `due_day` (15 por defecto) del mes siguiente
        due_month = month + 1 if month < 12 else 1
        due_year = year if month < 12 else year + 1
        due_last_day = calendar.monthrange(due_year, due_month)[1]
        due_date = date(due_year, due_month, min(int(config['due_day']), due_last_day))

        # Create statutory obligations
        if total_paye > 0:
            StatutoryObligation.objects.update_or_create(
                tenant=tenant,
                obligation_type=config['income_tax']['code'],
                period_month=month,
                period_year=year,
                defaults={
                    'amount_due': total_paye,
                    'due_date': due_date,
                    'status': 'pending',
                },
            )

        nssf_total = total_nssf_employee + total_nssf_employer
        if nssf_total > 0:
            StatutoryObligation.objects.update_or_create(
                tenant=tenant,
                obligation_type=config['social_security']['code'],
                period_month=month,
                period_year=year,
                defaults={
                    'amount_due': nssf_total,
                    'due_date': due_date,
                    'status': 'pending',
                },
            )

        logger.info(
            "Payroll run for %s/%s/%s complete. Gross: %s, PAYE: %s, Net: %s",
            tenant, month, year, total_gross, total_paye, total_net,
        )
        return payroll_run
