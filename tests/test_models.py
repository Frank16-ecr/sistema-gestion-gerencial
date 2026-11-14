"""Basic model creation tests for the Zelani Finance Module."""
from django.test import TestCase
from django.contrib.auth import get_user_model

User = get_user_model()


class TenantModelTest(TestCase):
    def setUp(self):
        self.tenant = __import__('tenants.models', fromlist=['Tenant']).Tenant.objects.create(
            name="Test Tenant",
            slug="test-tenant",
        )

    def test_tenant_creation(self):
        from tenants.models import Tenant
        self.assertEqual(Tenant.objects.count(), 1)
        self.assertEqual(str(self.tenant), "Test Tenant")

    def test_tenant_setting_creation(self):
        from tenants.models import TenantSetting
        setting = TenantSetting.objects.create(
            tenant=self.tenant,
            setting_key="tax_rate",
            setting_value={"rate": 18},
        )
        self.assertEqual(setting.setting_key, "tax_rate")


class AccountModelTest(TestCase):
    def setUp(self):
        from tenants.models import Tenant
        self.tenant = Tenant.objects.create(name="Acct Tenant", slug="acct-tenant")

    def test_account_creation(self):
        from finance.accounts.models import Account
        account = Account.objects.create(
            tenant=self.tenant,
            code="1001",
            name="Cash",
            category="asset",
        )
        self.assertEqual(str(account), "1001 - Cash")

    def test_journal_entry_creation(self):
        from finance.accounts.models import Account, JournalEntry, JournalLine
        from datetime import date
        user = User.objects.create_user(username="testuser", password="pass")
        account = Account.objects.create(
            tenant=self.tenant, code="1001", name="Cash", category="asset"
        )
        income_account = Account.objects.create(
            tenant=self.tenant, code="4001", name="Revenue", category="income"
        )
        entry = JournalEntry.objects.create(
            tenant=self.tenant,
            entry_date=date.today(),
            reference="JE-001",
            created_by=user,
        )
        JournalLine.objects.create(
            tenant=self.tenant,
            journal_entry=entry,
            account=account,
            debit_amount=1000,
        )
        JournalLine.objects.create(
            tenant=self.tenant,
            journal_entry=entry,
            account=income_account,
            credit_amount=1000,
        )
        self.assertEqual(entry.lines.count(), 2)


class FeeNoteModelTest(TestCase):
    def setUp(self):
        import uuid
        from tenants.models import Tenant
        self.tenant = Tenant.objects.create(name="Invoice Tenant", slug="invoice-tenant")
        self.user = User.objects.create_user(username="invoiceuser", password="pass")
        self.claim_id = uuid.uuid4()
        self.insurer_id = uuid.uuid4()

    def test_fee_note_creation(self):
        from finance.invoicing.models import FeeNote
        fn = FeeNote.objects.create(
            tenant=self.tenant,
            claim_id=self.claim_id,
            fee_note_number="FN-001",
            insurer_id=self.insurer_id,
            insurer_name="Test Insurer",
            invoice_amount=1000,
            vat_amount=180,
            total_amount=1180,
            base_currency_amount=1180,
            balance_due=1180,
            created_by=self.user,
        )
        self.assertEqual(str(fn), "FN-001")
        self.assertEqual(fn.status, "draft")


class PaymentModelTest(TestCase):
    def setUp(self):
        import uuid
        from tenants.models import Tenant
        from finance.invoicing.models import FeeNote
        self.tenant = Tenant.objects.create(name="Pay Tenant", slug="pay-tenant")
        self.user = User.objects.create_user(username="payuser", password="pass")
        self.fee_note = FeeNote.objects.create(
            tenant=self.tenant,
            claim_id=uuid.uuid4(),
            fee_note_number="FN-PAY-001",
            insurer_id=uuid.uuid4(),
            invoice_amount=1000,
            vat_amount=0,
            total_amount=1000,
            base_currency_amount=1000,
            balance_due=1000,
        )

    def test_payment_creation(self):
        from finance.payments.models import FeeNotePayment
        from datetime import date
        payment = FeeNotePayment.objects.create(
            tenant=self.tenant,
            fee_note=self.fee_note,
            payment_currency="UGX",
            amount_received_foreign=500,
            exchange_rate=1,
            base_currency_received=500,
            payment_date=date.today(),
            payment_method="bank_transfer",
            recorded_by=self.user,
        )
        self.assertEqual(payment.amount_received_foreign, 500)


class ExpenseModelTest(TestCase):
    def setUp(self):
        from tenants.models import Tenant
        self.tenant = Tenant.objects.create(name="Exp Tenant", slug="exp-tenant")
        self.user = User.objects.create_user(username="expuser", password="pass")

    def test_expense_creation(self):
        from finance.expenses.models import Expense
        from datetime import date
        expense = Expense.objects.create(
            tenant=self.tenant,
            description="Office rent",
            category="rent",
            amount=500000,
            expense_date=date.today(),
            submitted_by=self.user,
        )
        self.assertEqual(expense.status, "pending")


class PayrollModelTest(TestCase):
    def setUp(self):
        from tenants.models import Tenant
        self.tenant = Tenant.objects.create(name="PR Tenant", slug="pr-tenant")
        self.user = User.objects.create_user(username="pruser", password="pass")

    def test_employee_profile_creation(self):
        from finance.payroll.models import EmployeePayrollProfile
        from datetime import date
        profile = EmployeePayrollProfile.objects.create(
            tenant=self.tenant,
            user=self.user,
            employee_number="EMP001",
            gross_salary=2000000,
            start_date=date.today(),
        )
        self.assertEqual(profile.employee_number, "EMP001")


class BankingModelTest(TestCase):
    def setUp(self):
        from tenants.models import Tenant
        self.tenant = Tenant.objects.create(name="Bank Tenant", slug="bank-tenant")

    def test_bank_account_creation(self):
        from finance.banking.models import BankAccount
        account = BankAccount.objects.create(
            tenant=self.tenant,
            account_name="Main Account",
            bank_name="Stanbic Bank",
            account_number="9876543210",
            currency="UGX",
        )
        self.assertTrue(account.is_active)


class FxModelTest(TestCase):
    def setUp(self):
        from tenants.models import Tenant
        self.tenant = Tenant.objects.create(name="FX Tenant", slug="fx-tenant")
        self.user = User.objects.create_user(username="fxuser", password="pass")

    def test_exchange_rate_creation(self):
        from finance.fx.models import ExchangeRate
        from datetime import date
        rate = ExchangeRate.objects.create(
            tenant=self.tenant,
            from_currency="USD",
            to_currency="UGX",
            rate=3700,
            rate_date=date.today(),
            created_by=self.user,
        )
        self.assertEqual(rate.from_currency, "USD")


class AuditModelTest(TestCase):
    def setUp(self):
        from tenants.models import Tenant
        self.tenant = Tenant.objects.create(name="Audit Tenant", slug="audit-tenant")
        self.user = User.objects.create_user(username="audituser", password="pass")

    def test_audit_log_creation(self):
        from finance.audit.models import AuditLog
        log = AuditLog.objects.create(
            tenant=self.tenant,
            action="create",
            model_name="FeeNote",
            object_id="1",
            performed_by=self.user,
            notes="Created fee note",
        )
        self.assertEqual(log.action, "create")
