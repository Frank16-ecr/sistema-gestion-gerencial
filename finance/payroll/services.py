import logging
from decimal import Decimal
from django.utils import timezone

logger = logging.getLogger(__name__)


class PayrollService:

    @staticmethod
    def calculate_paye(taxable_income):
        """
        Uganda PAYE calculation using tax bands (monthly income in UGX).
        Uganda tax bands (monthly):
        - 0 - 235,000: 0%
        - 235,001 - 335,000: 10%
        - 335,001 - 410,000: 20%
        - 410,001 - 10,000,000: 30%
        - Above 10,000,000: 40%
        """
        income = Decimal(str(taxable_income))
        paye = Decimal('0')

        if income <= Decimal('235000'):
            paye = Decimal('0')
        elif income <= Decimal('335000'):
            paye = (income - Decimal('235000')) * Decimal('0.10')
        elif income <= Decimal('410000'):
            paye = (Decimal('335000') - Decimal('235000')) * Decimal('0.10')
            paye += (income - Decimal('335000')) * Decimal('0.20')
        elif income <= Decimal('10000000'):
            paye = (Decimal('335000') - Decimal('235000')) * Decimal('0.10')
            paye += (Decimal('410000') - Decimal('335000')) * Decimal('0.20')
            paye += (income - Decimal('410000')) * Decimal('0.30')
        else:
            paye = (Decimal('335000') - Decimal('235000')) * Decimal('0.10')
            paye += (Decimal('410000') - Decimal('335000')) * Decimal('0.20')
            paye += (Decimal('10000000') - Decimal('410000')) * Decimal('0.30')
            paye += (income - Decimal('10000000')) * Decimal('0.40')

        return paye.quantize(Decimal('0.01'))

    @staticmethod
    def calculate_nssf(gross_salary):
        """
        NSSF calculation:
        - Employee: 5% of gross salary
        - Employer: 10% of gross salary
        """
        gross = Decimal(str(gross_salary))
        employee_contribution = (gross * Decimal('0.05')).quantize(Decimal('0.01'))
        employer_contribution = (gross * Decimal('0.10')).quantize(Decimal('0.01'))
        return employee_contribution, employer_contribution

    @staticmethod
    def run_monthly_payroll(tenant, month, year, user):
        """
        Loads active employees, calculates PAYE/NSSF,
        saves payroll run + lines, creates statutory obligations.
        """
        from finance.payroll.models import EmployeePayrollProfile, PayrollRun, PayrollLine
        from finance.statutory.models import StatutoryObligation
        from datetime import date
        import calendar

        payroll_run, created = PayrollRun.objects.get_or_create(
            tenant=tenant,
            month=month,
            year=year,
            defaults={'status': 'draft', 'created_by': user},
        )

        if not created and payroll_run.status != 'draft':
            logger.warning("Payroll run for %s/%s already exists and is not in draft state.", month, year)
            return payroll_run

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

            paye = PayrollService.calculate_paye(taxable_income)
            nssf_employee, nssf_employer = PayrollService.calculate_nssf(gross_salary)
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

        # Determine due date (15th of following month)
        due_month = month + 1 if month < 12 else 1
        due_year = year if month < 12 else year + 1
        due_last_day = calendar.monthrange(due_year, due_month)[1]
        paye_due_date = date(due_year, due_month, min(15, due_last_day))
        nssf_due_date = date(due_year, due_month, min(15, due_last_day))

        # Create statutory obligations
        if total_paye > 0:
            StatutoryObligation.objects.update_or_create(
                tenant=tenant,
                obligation_type='paye',
                period_month=month,
                period_year=year,
                defaults={
                    'amount_due': total_paye,
                    'due_date': paye_due_date,
                    'status': 'pending',
                },
            )

        nssf_total = total_nssf_employee + total_nssf_employer
        if nssf_total > 0:
            StatutoryObligation.objects.update_or_create(
                tenant=tenant,
                obligation_type='nssf',
                period_month=month,
                period_year=year,
                defaults={
                    'amount_due': nssf_total,
                    'due_date': nssf_due_date,
                    'status': 'pending',
                },
            )

        logger.info(
            "Payroll run for %s/%s/%s complete. Gross: %s, PAYE: %s, Net: %s",
            tenant, month, year, total_gross, total_paye, total_net,
        )
        return payroll_run
