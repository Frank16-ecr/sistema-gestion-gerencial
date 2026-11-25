"""Test key service methods."""
import uuid
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

User = get_user_model()


class FeeNoteServiceTest(TestCase):
    def setUp(self):
        from tenants.models import Tenant
        self.tenant = Tenant.objects.create(name="Svc Tenant", slug="svc-tenant")
        self.user = User.objects.create_user(username="svcuser", password="pass")

    def test_generate_from_claim(self):
        from finance.invoicing.services import FeeNoteService
        claim_data = {
            'claim_id': uuid.uuid4(),
            'insurer_id': uuid.uuid4(),
            'insurer_name': 'APA Insurance',
            'insurer_email': 'billing@apa.com',
            'invoice_currency': 'UGX',
            'invoice_amount': Decimal('500000'),
            'vat_amount': Decimal('90000'),
            'exchange_rate': Decimal('1'),
            'due_date': date(2025, 6, 30),
        }
        fee_note = FeeNoteService.generate_from_claim(claim_data, self.tenant, self.user)
        self.assertEqual(fee_note.status, 'draft')
        self.assertEqual(fee_note.tenant, self.tenant)
        self.assertEqual(fee_note.invoice_amount, Decimal('500000'))

    def test_void_fee_note(self):
        from finance.invoicing.models import FeeNote
        from finance.invoicing.services import FeeNoteService
        fn = FeeNote.objects.create(
            tenant=self.tenant,
            claim_id=uuid.uuid4(),
            fee_note_number="FN-VOID-001",
            insurer_id=uuid.uuid4(),
            invoice_amount=1000,
            vat_amount=0,
            total_amount=1000,
            base_currency_amount=1000,
            balance_due=1000,
        )
        FeeNoteService.void_fee_note(fn, "Test void", self.user)
        fn.refresh_from_db()
        self.assertTrue(fn.is_void)
        self.assertEqual(fn.status, 'void')

    def test_update_overdue_statuses(self):
        from finance.invoicing.models import FeeNote
        from finance.invoicing.services import FeeNoteService
        fn = FeeNote.objects.create(
            tenant=self.tenant,
            claim_id=uuid.uuid4(),
            fee_note_number="FN-OD-001",
            insurer_id=uuid.uuid4(),
            invoice_amount=1000,
            vat_amount=0,
            total_amount=1000,
            base_currency_amount=1000,
            balance_due=1000,
            status='sent',
            due_date=date(2020, 1, 1),  # Very old date
        )
        FeeNoteService.update_overdue_statuses(self.tenant)
        fn.refresh_from_db()
        self.assertEqual(fn.status, 'overdue_3')


class PayrollServiceTest(TestCase):
    def setUp(self):
        from tenants.models import Tenant
        self.tenant = Tenant.objects.create(name="PR Svc Tenant", slug="pr-svc-tenant")
        self.user = User.objects.create_user(username="prsvcuser", password="pass")

    def test_calculate_paye_zero(self):
        from finance.payroll.services import PayrollService
        paye = PayrollService.calculate_paye(Decimal('200000'))
        self.assertEqual(paye, Decimal('0.00'))

    def test_calculate_paye_first_band(self):
        from finance.payroll.services import PayrollService

        # 300,000 - 235,000 = 65,000 * 10% = 6,500
        paye = PayrollService.calculate_paye(Decimal('300000'))
        self.assertEqual(paye, Decimal('6500.00'))

    def test_calculate_paye_third_band(self):
        from finance.payroll.services import PayrollService

        # Taxable: 2,000,000
        paye = PayrollService.calculate_paye(Decimal('2000000'))
        # (335000-235000)*10% + (410000-335000)*20% + (2000000-410000)*30%
        # = 10000 + 15000 + 477000 = 502000
        self.assertEqual(paye, Decimal('502000.00'))

    def test_calculate_nssf(self):
        from finance.payroll.services import PayrollService
        employee, employer = PayrollService.calculate_nssf(Decimal('2000000'))
        self.assertEqual(employee, Decimal('100000.00'))
        self.assertEqual(employer, Decimal('200000.00'))

    def test_run_monthly_payroll(self):
        from finance.payroll.models import EmployeePayrollProfile
        from finance.payroll.services import PayrollService
        EmployeePayrollProfile.objects.create(
            tenant=self.tenant,
            user=self.user,
            employee_number="EMP001",
            gross_salary=Decimal('2000000'),
            start_date=date.today(),
        )
        payroll_run = PayrollService.run_monthly_payroll(self.tenant, 6, 2025, self.user)
        self.assertIsNotNone(payroll_run)
        self.assertEqual(payroll_run.lines.count(), 1)
        self.assertGreater(payroll_run.total_gross, 0)


class PaymentServiceTest(TestCase):
    def setUp(self):
        import uuid

        from finance.invoicing.models import FeeNote
        from tenants.models import Tenant, TenantSetting
        self.tenant = Tenant.objects.create(name="Pay Svc Tenant", slug="pay-svc-tenant")
        # Empresa ugandesa: contabiliza en UGX y factura en USD.
        TenantSetting.objects.create(tenant=self.tenant, setting_key='base_currency', setting_value='UGX')
        self.user = User.objects.create_user(username="paysvcuser", password="pass")
        self.fee_note = FeeNote.objects.create(
            tenant=self.tenant,
            claim_id=uuid.uuid4(),
            fee_note_number="FN-SVC-001",
            insurer_id=uuid.uuid4(),
            invoice_currency='USD',
            invoice_amount=Decimal('1000'),
            vat_amount=Decimal('0'),
            total_amount=Decimal('1000'),
            exchange_rate_at_issue=Decimal('3600'),
            base_currency_amount=Decimal('3600000'),
            balance_due=Decimal('1000'),
        )

    def test_record_payment(self):
        from finance.payments.services import PaymentService
        payload = {
            'amount_received_foreign': Decimal('1000'),
            'exchange_rate': Decimal('3700'),
            'payment_currency': 'USD',
            'payment_date': date.today(),
            'payment_method': 'bank_transfer',
        }
        payment = PaymentService.record_payment(self.fee_note, payload, self.user)
        self.assertEqual(payment.amount_received_foreign, Decimal('1000'))
        # FX gain = (3700 - 3600) * 1000 = 100,000
        self.assertEqual(payment.fx_gain_loss, Decimal('100000.00'))
        self.fee_note.refresh_from_db()
        self.assertEqual(self.fee_note.status, 'paid')

    def test_calculate_fx_gain_loss(self):
        from finance.payments.models import FeeNotePayment
        from finance.payments.services import PaymentService
        payment = FeeNotePayment(
            fee_note=self.fee_note,
            payment_currency='USD',
            amount_received_foreign=Decimal('500'),
            exchange_rate=Decimal('3800'),
            base_currency_received=Decimal('1900000'),
        )
        gain_loss = PaymentService.calculate_fx_gain_loss(self.fee_note, payment)
        # (3800 - 3600) * 500 = 100000
        self.assertEqual(gain_loss, Decimal('100000.00'))
