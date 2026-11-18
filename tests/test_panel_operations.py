"""Pruebas de las pantallas de cobros, nomina, tesoreria y contabilidad del panel."""

from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.urls import reverse

from finance.accounts.models import Account, JournalEntry
from finance.banking.models import BankAccount, BankReconciliation, Cheque, PettyCashTransaction
from finance.invoicing.models import FeeNote
from finance.payments.models import FeeNotePayment, WHTCredit
from finance.payroll.models import EmployeeAllowance, EmployeePayrollProfile, PayrollRun
from finance.security.models import UserTenantRole

from .test_panel import PanelTestBase

User = get_user_model()


def make_note(tenant, number='FN-1', status='sent', total='1000.00', **kw):
    total = Decimal(total)
    return FeeNote.objects.create(
        tenant=tenant,
        fee_note_number=number,
        claim_id='11111111-1111-1111-1111-111111111111',
        insurer_id='22222222-2222-2222-2222-222222222222',
        insurer_name='Aseguradora X',
        insurer_email='x@example.com',
        invoice_currency='USD',
        invoice_amount=total,
        vat_amount=0,
        total_amount=total,
        exchange_rate_at_issue=Decimal('3700'),
        base_currency_amount=total * 3700,
        ugx_amount_efris=total * 3700,
        balance_due=total,
        status=status,
        due_date=date(2026, 12, 31),
        **kw,
    )


class OpsBase(PanelTestBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.manager = User.objects.create_user('gerente', password='pass12345')
        UserTenantRole.objects.create(tenant=cls.t1, user=cls.manager, role='manager')
        cls.analyst = User.objects.create_user('analista', password='pass12345')
        UserTenantRole.objects.create(tenant=cls.t1, user=cls.analyst, role='analyst')
        cls.auditor = User.objects.create_user('auditor', password='pass12345')
        UserTenantRole.objects.create(tenant=cls.t1, user=cls.auditor, role='auditor')

    def login(self, name='gerente'):
        self.client.login(username=name, password='pass12345')
        session = self.client.session
        session['panel_tenant_id'] = self.t1.id
        session.save()


class EveryPageRendersTests(OpsBase):
    def test_all_list_pages_render_for_manager(self):
        self.login()
        for name in (
            'invoices',
            'invoice-create',
            'payments',
            'wht',
            'employees',
            'employee-create',
            'payroll',
            'payroll-create',
            'bank-accounts',
            'bank-account-create',
            'reconciliations',
            'reconciliation-create',
            'petty-cash',
            'cheques',
            'cheque-create',
            'chart-of-accounts',
            'account-create',
            'journal',
            'journal-create',
            'reports',
        ):
            with self.subTest(name):
                self.assertEqual(self.client.get(reverse(f'panel:{name}')).status_code, 200)
        for key in ('resultados', 'pendientes', 'nomina'):
            self.assertEqual(self.client.get(reverse('panel:reports') + f'?r={key}').status_code, 200)

    def test_viewer_can_read_but_not_write(self):
        self.login('lector')
        self.assertEqual(self.client.get(reverse('panel:invoices')).status_code, 200)
        self.assertEqual(self.client.get(reverse('panel:invoice-create')).status_code, 403)
        self.assertEqual(self.client.get(reverse('panel:bank-account-create')).status_code, 403)
        self.assertEqual(self.client.post(reverse('panel:invoice-refresh')).status_code, 403)

    def test_payroll_hidden_from_analyst_and_viewer(self):
        for name in ('analista', 'lector'):
            self.login(name)
            self.assertEqual(self.client.get(reverse('panel:employees')).status_code, 403)
            self.assertEqual(self.client.get(reverse('panel:payroll')).status_code, 403)
            self.assertNotContains(self.client.get(reverse('panel:invoices')), 'Corridas de nómina')
        self.login('auditor')
        self.assertEqual(self.client.get(reverse('panel:payroll')).status_code, 200)
        self.assertEqual(self.client.get(reverse('panel:payroll-create')).status_code, 403)


class BillingTests(OpsBase):
    def test_create_note_computes_totals_and_defaults(self):
        self.login()
        response = self.client.post(
            reverse('panel:invoice-create'),
            {
                'fee_note_number': 'FN-NEW',
                'insurer_name': 'Seguros',
                'insurer_email': 's@example.com',
                'invoice_currency': 'USD',
                'invoice_amount': '1000',
                'vat_amount': '180',
                'exchange_rate_at_issue': '3700',
                'due_date': '2026-12-31',
            },
        )
        note = FeeNote.objects.get(fee_note_number='FN-NEW')
        self.assertRedirects(response, reverse('panel:invoice-detail', args=[note.pk]))
        self.assertEqual(
            (note.status, note.tenant, note.total_amount, note.balance_due),
            ('draft', self.t1, Decimal('1180.00'), Decimal('1180.00')),
        )
        self.assertEqual(note.base_currency_amount, Decimal('4366000.00'))
        self.assertTrue(note.claim_id)

    def test_duplicate_number_and_bad_amount_rejected(self):
        self.login()
        make_note(self.t1, 'FN-DUP')
        data = {
            'fee_note_number': 'FN-DUP',
            'invoice_currency': 'USD',
            'invoice_amount': '0',
            'vat_amount': '0',
            'exchange_rate_at_issue': '1',
        }
        response = self.client.post(reverse('panel:invoice-create'), data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(FeeNote.objects.filter(fee_note_number='FN-DUP').count(), 1)

    def test_efris_then_send_and_edit_only_draft(self):
        self.login()
        note = make_note(self.t1, status='draft')
        self.client.post(reverse('panel:invoice-action', args=[note.pk, 'efris']))
        note.refresh_from_db()
        self.assertNotEqual(note.status, 'draft')
        self.assertEqual(self.client.get(reverse('panel:invoice-edit', args=[note.pk])).status_code, 302)

    def test_payment_updates_balance_and_creates_wht(self):
        self.login()
        note = make_note(self.t1)
        url = reverse('panel:payment-create', args=[note.pk])
        base = {
            'amount_received_foreign': '400',
            'exchange_rate': '3750',
            'payment_date': '2026-11-01',
            'payment_method': 'bank_transfer',
        }
        self.client.post(url, {**base, 'wht_deducted': 'on', 'wht_amount': '24', 'wht_cert_number': 'C-1'})
        note.refresh_from_db()
        self.assertEqual(
            (note.amount_paid, note.balance_due, note.status), (Decimal('400.00'), Decimal('600.00'), 'partial')
        )
        self.assertEqual(WHTCredit.objects.get().cert_number, 'C-1')
        self.assertEqual(self.client.get(reverse('panel:payments')).status_code, 200)

    def test_payment_cannot_exceed_balance_or_skip_wht_data(self):
        self.login()
        note = make_note(self.t1)
        url = reverse('panel:payment-create', args=[note.pk])
        base = {'exchange_rate': '3700', 'payment_date': '2026-11-01', 'payment_method': 'cash'}
        self.client.post(url, {**base, 'amount_received_foreign': '1500'})
        self.client.post(url, {**base, 'amount_received_foreign': '100', 'wht_deducted': 'on'})
        self.assertFalse(FeeNotePayment.objects.exists())

    def test_cannot_pay_draft_note(self):
        self.login()
        note = make_note(self.t1, status='draft')
        response = self.client.post(reverse('panel:payment-create', args=[note.pk]), {})
        self.assertRedirects(response, reverse('panel:invoice-detail', args=[note.pk]))

    def test_void_needs_reason_and_no_payments(self):
        self.login()
        note = make_note(self.t1)
        url = reverse('panel:invoice-action', args=[note.pk, 'void'])
        self.client.post(url, {'reason': ''})
        note.refresh_from_db()
        self.assertFalse(note.is_void)
        self.client.post(url, {'reason': 'Error de captura'})
        note.refresh_from_db()
        self.assertTrue(note.is_void)
        paid = make_note(self.t1, 'FN-2')
        self.client.post(
            reverse('panel:payment-create', args=[paid.pk]),
            {
                'amount_received_foreign': '10',
                'exchange_rate': '3700',
                'payment_date': '2026-11-01',
                'payment_method': 'cash',
            },
        )
        self.client.post(reverse('panel:invoice-action', args=[paid.pk, 'void']), {'reason': 'x'})
        paid.refresh_from_db()
        self.assertFalse(paid.is_void)

    def test_reminder_is_recorded(self):
        self.login()
        note = make_note(self.t1)
        self.client.post(
            reverse('panel:reminder-create', args=[note.pk]), {'reminder_type': 'friendly', 'sent_to': 'x@example.com'}
        )
        self.assertEqual(note.reminders.count(), 1)

    def test_other_tenant_note_is_404_and_untouched(self):
        self.login()
        other = make_note(self.t2, 'FN-OTHER')
        self.assertEqual(self.client.get(reverse('panel:invoice-detail', args=[other.pk])).status_code, 404)
        self.assertEqual(
            self.client.post(reverse('panel:invoice-action', args=[other.pk, 'void']), {'reason': 'x'}).status_code, 404
        )
        self.assertNotContains(self.client.get(reverse('panel:invoices')), 'FN-OTHER')

    def test_wht_toggle(self):
        self.login()
        note = make_note(self.t1)
        pay = FeeNotePayment.objects.create(
            tenant=self.t1,
            fee_note=note,
            payment_date=date(2026, 11, 1),
            payment_currency='USD',
            amount_received_foreign=Decimal('10'),
            exchange_rate=Decimal('3700'),
            base_currency_received=Decimal('37000'),
            payment_method='cash',
        )
        credit = WHTCredit.objects.create(
            tenant=self.t1, payment=pay, amount=Decimal('1'), cert_number='C-9', period_year=2026, period_month=11
        )
        self.client.post(reverse('panel:wht-toggle', args=[credit.pk]))
        credit.refresh_from_db()
        self.assertTrue(credit.is_utilised)
        self.client.login(username='lector', password='pass12345')
        self.assertEqual(self.client.post(reverse('panel:wht-toggle', args=[credit.pk])).status_code, 403)


class PayrollTests(OpsBase):
    def make_employee(self, number='E1', salary='2000000.00'):
        user = User.objects.create_user(f'emp{number}', password='x')
        UserTenantRole.objects.create(tenant=self.t1, user=user, role='viewer')
        return EmployeePayrollProfile.objects.create(
            tenant=self.t1, user=user, employee_number=number, gross_salary=Decimal(salary), start_date=date(2026, 1, 1)
        )

    def test_create_employee_and_allowance(self):
        self.login()
        user = User.objects.create_user('nuevo', password='x')
        UserTenantRole.objects.create(tenant=self.t1, user=user, role='viewer')
        self.client.post(
            reverse('panel:employee-create'),
            {
                'user': user.pk,
                'employee_number': 'E9',
                'gross_salary': '1500000',
                'start_date': '2026-01-01',
                'is_active': 'on',
            },
        )
        emp = EmployeePayrollProfile.objects.get(employee_number='E9')
        self.assertEqual(emp.tenant, self.t1)
        self.client.post(
            reverse('panel:allowance-add', args=[emp.pk]),
            {'allowance_type': 'transport', 'amount': '50000', 'is_taxable': 'on'},
        )
        self.assertEqual(emp.allowances.count(), 1)
        self.assertEqual(self.client.get(reverse('panel:employee-detail', args=[emp.pk])).status_code, 200)

    def test_employee_user_must_have_role_in_tenant(self):
        self.login()
        stranger = User.objects.create_user('extraño', password='x')
        self.client.post(
            reverse('panel:employee-create'),
            {'user': stranger.pk, 'employee_number': 'E8', 'gross_salary': '1', 'start_date': '2026-01-01'},
        )
        self.assertFalse(EmployeePayrollProfile.objects.filter(employee_number='E8').exists())

    def test_run_approve_pay_flow(self):
        self.login()
        emp = self.make_employee()
        EmployeeAllowance.objects.create(employee=emp, allowance_type='transport', amount=Decimal('100000'))
        self.client.post(reverse('panel:payroll-create'), {'month': 10, 'year': 2026})
        run = PayrollRun.objects.get(tenant=self.t1, month=10, year=2026)
        self.assertEqual(run.lines.count(), 1)
        self.assertGreater(run.total_net, 0)
        self.assertEqual(self.client.get(reverse('panel:payroll-detail', args=[run.pk])).status_code, 200)
        self.client.post(reverse('panel:payroll-action', args=[run.pk, 'pay']))  # no se puede saltar la aprobacion
        run.refresh_from_db()
        self.assertEqual(run.status, 'draft')
        self.client.post(reverse('panel:payroll-action', args=[run.pk, 'approve']))
        self.client.post(reverse('panel:payroll-action', args=[run.pk, 'pay']))
        run.refresh_from_db()
        self.assertEqual((run.status, run.approved_by), ('paid', self.manager))
        response = self.client.post(reverse('panel:payroll-create'), {'month': 10, 'year': 2026})
        self.assertEqual(response.status_code, 200)  # ya pagada: no se recalcula

    def test_run_without_employees_rejected(self):
        self.login()
        response = self.client.post(reverse('panel:payroll-create'), {'month': 10, 'year': 2026})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(PayrollRun.objects.exists())

    def test_other_tenant_employee_not_reachable(self):
        self.login()
        user = User.objects.create_user('ajeno', password='x')
        emp = EmployeePayrollProfile.objects.create(
            tenant=self.t2, user=user, employee_number='X', gross_salary=1, start_date=date(2026, 1, 1)
        )
        self.assertEqual(self.client.get(reverse('panel:employee-detail', args=[emp.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse('panel:allowance-add', args=[emp.pk]), {}).status_code, 404)


class TreasuryTests(OpsBase):
    def account(self, kind='current', balance='1000.00', name='Cuenta'):
        return BankAccount.objects.create(
            tenant=self.t1,
            account_name=name,
            bank_name='Banco',
            account_number=name,
            currency='USD',
            account_type=kind,
            opening_balance=Decimal(balance),
            current_balance=Decimal(balance),
        )

    def test_create_account_sets_balance(self):
        self.login()
        self.client.post(
            reverse('panel:bank-account-create'),
            {
                'account_name': 'Principal',
                'bank_name': 'B',
                'account_number': '1',
                'currency': 'USD',
                'account_type': 'current',
                'opening_balance': '500',
                'is_active': 'on',
            },
        )
        self.assertEqual(BankAccount.objects.get().current_balance, Decimal('500.00'))

    def test_edit_cannot_change_opening_balance(self):
        self.login()
        acc = self.account()
        self.client.post(
            reverse('panel:bank-account-edit', args=[acc.pk]),
            {
                'account_name': 'Nuevo nombre',
                'bank_name': 'B',
                'account_number': '1',
                'account_type': 'current',
                'opening_balance': '99999',
                'currency': 'EUR',
                'is_active': 'on',
            },
        )
        acc.refresh_from_db()
        self.assertEqual(
            (acc.account_name, acc.opening_balance, acc.currency), ('Nuevo nombre', Decimal('1000.00'), 'USD')
        )

    def test_petty_cash_moves_balance_and_blocks_overdraw(self):
        self.login()
        box = self.account('petty_cash', '100.00', 'Caja')
        data = {
            'bank_account': box.pk,
            'transaction_type': 'withdrawal',
            'amount': '30',
            'description': 'Café',
            'transaction_date': '2026-11-01',
        }
        self.client.post(reverse('panel:petty-cash-create'), data)
        self.client.post(reverse('panel:petty-cash-create'), {**data, 'amount': '500'})
        self.client.post(reverse('panel:petty-cash-create'), {**data, 'transaction_type': 'top_up', 'amount': '10'})
        box.refresh_from_db()
        self.assertEqual(box.current_balance, Decimal('80.00'))
        self.assertEqual(PettyCashTransaction.objects.count(), 2)

    def test_petty_cash_rejects_regular_account(self):
        self.login()
        acc = self.account()
        self.client.post(
            reverse('panel:petty-cash-create'),
            {
                'bank_account': acc.pk,
                'transaction_type': 'top_up',
                'amount': '5',
                'description': 'x',
                'transaction_date': '2026-11-01',
            },
        )
        self.assertFalse(PettyCashTransaction.objects.exists())

    def test_cheque_flow_updates_balance_once(self):
        self.login()
        acc = self.account()
        self.client.post(
            reverse('panel:cheque-create'),
            {
                'bank_account': acc.pk,
                'cheque_type': 'issued',
                'cheque_number': '001',
                'amount': '200',
                'payee_payer': 'Proveedor',
                'issue_date': '2026-11-01',
            },
        )
        cheque = Cheque.objects.get()
        self.assertEqual(cheque.status, 'pending')
        self.client.post(reverse('panel:cheque-action', args=[cheque.pk, 'clear']))
        self.client.post(reverse('panel:cheque-action', args=[cheque.pk, 'clear']))
        acc.refresh_from_db()
        cheque.refresh_from_db()
        self.assertEqual((acc.current_balance, cheque.status), (Decimal('800.00'), 'cleared'))
        self.assertIsNotNone(cheque.cleared_date)
        self.client.post(reverse('panel:cheque-action', args=[cheque.pk, 'bounce']))
        cheque.refresh_from_db()
        self.assertEqual(cheque.status, 'cleared')

    def test_duplicate_cheque_number_rejected(self):
        self.login()
        acc = self.account()
        data = {
            'bank_account': acc.pk,
            'cheque_type': 'receipt',
            'cheque_number': '7',
            'amount': '5',
            'payee_payer': 'X',
            'issue_date': '2026-11-01',
        }
        self.client.post(reverse('panel:cheque-create'), data)
        self.client.post(reverse('panel:cheque-create'), data)
        self.assertEqual(Cheque.objects.count(), 1)

    def test_reconciliation_lock_once(self):
        self.login()
        acc = self.account()
        data = {
            'bank_account': acc.pk,
            'period_month': 10,
            'period_year': 2026,
            'opening_balance': '0',
            'closing_balance_per_bank': '1000',
            'closing_balance_per_system': '990',
        }
        self.client.post(reverse('panel:reconciliation-create'), data)
        self.client.post(reverse('panel:reconciliation-create'), data)  # duplicado del periodo
        rec = BankReconciliation.objects.get()
        self.assertEqual(self.client.get(reverse('panel:reconciliation-detail', args=[rec.pk])).status_code, 200)
        self.client.post(reverse('panel:reconciliation-lock', args=[rec.pk]))
        rec.refresh_from_db()
        self.assertEqual((rec.status, rec.locked_by), ('locked', self.manager))

    def test_other_tenant_cheque_untouched(self):
        self.login()
        acc = BankAccount.objects.create(
            tenant=self.t2,
            account_name='Ajena',
            bank_name='B',
            account_number='9',
            currency='USD',
            opening_balance=1,
            current_balance=1,
        )
        cheque = Cheque.objects.create(
            tenant=self.t2,
            bank_account=acc,
            cheque_type='receipt',
            cheque_number='1',
            amount=Decimal('5'),
            payee_payer='X',
            issue_date=date(2026, 1, 1),
        )
        self.assertEqual(self.client.post(reverse('panel:cheque-action', args=[cheque.pk, 'clear'])).status_code, 404)


class AccountingTests(OpsBase):
    def setUp(self):
        self.cash = Account.objects.create(tenant=self.t1, code='1000', name='Caja', category='asset')
        self.sales = Account.objects.create(tenant=self.t1, code='4000', name='Ventas', category='income')

    def entry_data(self, debit='100', credit='100'):
        return {
            'entry_date': '2026-11-01',
            'reference': 'A-1',
            'description': 'Venta',
            'lines-TOTAL_FORMS': 4,
            'lines-INITIAL_FORMS': 0,
            'lines-MIN_NUM_FORMS': 0,
            'lines-MAX_NUM_FORMS': 1000,
            'lines-0-account': self.cash.pk,
            'lines-0-debit_amount': debit,
            'lines-1-account': self.sales.pk,
            'lines-1-credit_amount': credit,
        }

    def test_account_code_unique_per_tenant(self):
        self.login()
        data = {'code': '1000', 'name': 'Otra', 'category': 'asset', 'is_active': 'on'}
        self.client.post(reverse('panel:account-create'), data)
        self.assertEqual(Account.objects.filter(tenant=self.t1, code='1000').count(), 1)
        self.client.post(reverse('panel:account-create'), {**data, 'code': '2000'})
        self.assertTrue(Account.objects.filter(tenant=self.t1, code='2000').exists())

    def test_balanced_entry_saved_with_tenant_on_lines(self):
        self.login()
        self.client.post(reverse('panel:journal-create'), self.entry_data())
        entry = JournalEntry.objects.get()
        self.assertEqual(entry.lines.count(), 2)
        self.assertTrue(all(line.tenant == self.t1 for line in entry.lines.all()))
        self.assertEqual(self.client.get(reverse('panel:journal-detail', args=[entry.pk])).status_code, 200)

    def test_unbalanced_or_single_line_entry_rejected(self):
        self.login()
        self.client.post(reverse('panel:journal-create'), self.entry_data(credit='90'))
        data = self.entry_data()
        data.pop('lines-1-account')
        data.pop('lines-1-credit_amount')
        self.client.post(reverse('panel:journal-create'), data)
        both = self.entry_data()
        both['lines-0-credit_amount'] = '5'
        self.client.post(reverse('panel:journal-create'), both)
        self.assertFalse(JournalEntry.objects.exists())

    def test_cannot_use_other_tenant_account(self):
        self.login()
        foreign = Account.objects.create(tenant=self.t2, code='9', name='Ajena', category='asset')
        data = self.entry_data()
        data['lines-0-account'] = foreign.pk
        self.client.post(reverse('panel:journal-create'), data)
        self.assertFalse(JournalEntry.objects.exists())

    def test_void_entry_needs_reason_and_feeds_reports(self):
        self.login()
        self.client.post(reverse('panel:journal-create'), self.entry_data('500', '500'))
        entry = JournalEntry.objects.get()
        report = self.client.get(reverse('panel:reports') + '?r=resultados&start_date=2026-01-01&end_date=2026-12-31')
        self.assertContains(report, '500.00')
        self.client.post(reverse('panel:journal-void', args=[entry.pk]), {'reason': ''})
        entry.refresh_from_db()
        self.assertFalse(entry.is_void)
        self.client.post(reverse('panel:journal-void', args=[entry.pk]), {'reason': 'Duplicado'})
        entry.refresh_from_db()
        self.assertTrue(entry.is_void)
        report = self.client.get(reverse('panel:reports') + '?r=resultados&start_date=2026-01-01&end_date=2026-12-31')
        self.assertNotContains(report, '500.00')

    def test_report_rejects_inverted_dates(self):
        self.login()
        response = self.client.get(reverse('panel:reports') + '?r=resultados&start_date=2026-12-01&end_date=2026-01-01')
        self.assertContains(response, 'no puede ser anterior')

    def test_payroll_report_blocked_for_analyst(self):
        self.login('analista')
        response = self.client.get(reverse('panel:reports') + '?r=nomina', follow=True)
        self.assertNotContains(response, 'Bruto del año')
