"""Facturacion venezolana: IVA, IGTF, retenciones, notas, anulacion, libro de ventas y asientos.

Factura de referencia en USD, tasa BCV de emision 400 Bs/USD:
  general  2 x 100 = 200  -> IVA 16%       = 32
  reducida 1 x  50 =  50  -> IVA  8%       =  4
  lujo     1 x 100 = 100  -> IVA 16% + 15% = 31
  exento   1 x  30 =  30
  subtotal 380, IVA 67, total 447 USD = 178.800 Bs (IVA 26.800 Bs)
"""
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from rest_framework.test import APIClient

from finance.accounts.models import JournalEntry
from finance.accounts.services import create_chart_of_accounts
from finance.fx.models import ExchangeRate
from finance.reports.services import ReportService
from finance.sales import services
from finance.sales.models import Customer, Invoice, InvoiceLine, TaxpayerProfile
from finance.security.models import UserTenantRole
from finance.statutory.models import StatutoryObligation
from tenants.models import Tenant

User = get_user_model()
D = Decimal


class SalesBase(TestCase):

    def setUp(self):
        self.tenant = Tenant.objects.create(name='Comercial Andina', slug='andina')
        self.user = User.objects.create_user('ventas', password='x')
        create_chart_of_accounts(self.tenant)
        self.profile = TaxpayerProfile.objects.create(
            tenant=self.tenant, rif='J-12345678-9', legal_name='Comercial Andina, C.A.',
            fiscal_address='Caracas', is_special_taxpayer=True, igtf_collection_agent=True,
        )
        self.customer = Customer.objects.create(
            tenant=self.tenant, rif='J-87654321-0', name='Cliente Especial, C.A.', is_special_taxpayer=True,
            vat_withholding_percent=75,
        )
        for day, rate in ((2, '400'), (20, '420')):
            ExchangeRate.objects.create(tenant=self.tenant, from_currency='USD', to_currency='VES',
                                        rate=D(rate), rate_date=date(2026, 11, day), source='bcv')

    def draft(self, currency='USD', doc_type='invoice', related=None, lines=None, when=date(2026, 11, 5)):
        invoice = Invoice.objects.create(tenant=self.tenant, customer=self.customer, currency=currency,
                                         doc_type=doc_type, related_invoice=related, issue_date=when)
        for qty, price, cat in lines or [(2, '100', 'general'), (1, '50', 'reduced'), (1, '100', 'luxury'),
                                         (1, '30', 'exempt')]:
            InvoiceLine.objects.create(invoice=invoice, description=cat, quantity=qty, unit_price=D(price),
                                       tax_category=cat)
        return services.recalculate(invoice)

    def issued(self, **kwargs):
        return services.issue_invoice(self.draft(**kwargs), self.user)

    def obligation(self, code):
        row = StatutoryObligation.objects.filter(tenant=self.tenant, obligation_type=code,
                                                 period_month=11, period_year=2026).first()
        return row.amount_due if row else None

    def assert_books_balance(self):
        sheet = ReportService.get_balance_sheet(self.tenant, date(2026, 12, 31))
        self.assertTrue(sheet['is_balanced'], sheet)
        for entry in JournalEntry.objects.filter(tenant=self.tenant):
            debit = sum(line.debit_amount for line in entry.lines.all())
            credit = sum(line.credit_amount for line in entry.lines.all())
            self.assertEqual(debit, credit, entry.reference)


class IssueTests(SalesBase):

    def test_vat_by_category(self):
        inv = self.draft()
        self.assertEqual((inv.base_general, inv.tax_general), (D('200'), D('32')))
        self.assertEqual((inv.base_reduced, inv.tax_reduced), (D('50'), D('4')))
        self.assertEqual((inv.base_luxury, inv.tax_luxury), (D('100'), D('31')))
        self.assertEqual((inv.exempt_amount, inv.subtotal, inv.tax_total, inv.total),
                         (D('30'), D('380'), D('67'), D('447')))

    def test_issue_assigns_consecutive_numbers_and_bcv_rate(self):
        first, second = self.issued(), self.issued()
        note = self.issued(doc_type='credit_note', related=first, lines=[(1, '10', 'general')])
        self.assertEqual((first.number, first.control_number), ('00000001', '00-00000001'))
        self.assertEqual((second.number, second.control_number), ('00000002', '00-00000002'))
        # Las notas tienen su propia serie, pero el numero de control es unico y compartido.
        self.assertEqual((note.number, note.control_number), ('00000001', '00-00000003'))
        self.assertEqual(first.exchange_rate, D('400'))
        self.assertEqual((first.customer_rif, first.status), ('J-87654321-0', 'issued'))

    def test_issue_posts_journal_entry(self):
        inv = self.issued()
        lines = {line.account.code: (line.debit_amount, line.credit_amount) for line in inv.journal_entry.lines.all()}
        self.assertEqual(lines['1.1.03'], (D('178800.00'), D('0')))
        self.assertEqual(lines['4.1.01'], (D('0'), D('152000.00')))
        self.assertEqual(lines['2.1.02'], (D('0'), D('26800.00')))
        self.assertEqual(self.obligation('iva'), D('26800.00'))
        self.assert_books_balance()

    def test_issue_requirements(self):
        TaxpayerProfile.objects.all().delete()
        with self.assertRaisesMessage(services.InvoiceError, 'datos fiscales'):
            self.issued()

    def test_missing_bcv_rate(self):
        with self.assertRaisesMessage(services.InvoiceError, 'actualizar_tasa_bcv'):
            self.issued(when=date(2026, 10, 1))

    def test_missing_chart_of_accounts_blocks_issue(self):
        from finance.accounts.models import Account
        from finance.accounts.services import AccountingConfigError
        Account.objects.filter(tenant=self.tenant, code='2.1.02').delete()
        with self.assertRaises(AccountingConfigError):
            self.issued()
        self.assertEqual(Invoice.objects.get().status, 'draft')  # transaccion revertida


class PaymentTests(SalesBase):

    def test_usd_payment_with_igtf_and_fx_gain(self):
        inv = self.issued()
        pay = services.register_payment(inv, date(2026, 11, 20), D('447'), 'USD', 'zelle', 'Z-1', self.user)
        self.assertEqual(pay.applied_amount, D('447'))
        self.assertEqual(pay.amount_ves, D('187740.00'))
        self.assertEqual((pay.igtf_rate, pay.igtf_amount, pay.igtf_amount_ves), (D('3'), D('13.41'), D('5632.20')))
        self.assertEqual(pay.fx_difference_ves, D('8940.00'))
        inv.refresh_from_db()
        self.assertEqual((inv.status, inv.balance_due), ('paid', D('0')))
        self.assertEqual(self.obligation('igtf'), D('5632.20'))
        self.assert_books_balance()

    def test_bolivar_payment_of_usd_invoice(self):
        inv = self.issued()
        pay = services.register_payment(inv, date(2026, 11, 20), D('42000'), 'VES', user=self.user)
        self.assertEqual((pay.applied_amount, pay.igtf_amount), (D('100.00'), D('0')))
        self.assertEqual(pay.fx_difference_ves, D('2000.00'))
        inv.refresh_from_db()
        self.assertEqual((inv.status, inv.balance_due), ('partial', D('347.00')))
        self.assertIsNone(self.obligation('igtf'))
        self.assert_books_balance()

    def test_no_igtf_when_company_is_not_collection_agent(self):
        self.profile.igtf_collection_agent = False
        self.profile.save()
        pay = services.register_payment(self.issued(), date(2026, 11, 20), D('100'), 'USD', user=self.user)
        self.assertEqual(pay.igtf_amount, D('0'))

    def test_overpayment_and_invalid_payments(self):
        inv = self.issued()
        with self.assertRaisesMessage(services.InvoiceError, 'supera el saldo'):
            services.register_payment(inv, date(2026, 11, 20), D('500'), 'USD')
        with self.assertRaisesMessage(services.InvoiceError, 'anterior a la emision'):
            services.register_payment(inv, date(2026, 11, 1), D('10'), 'USD')
        with self.assertRaises(services.InvoiceError):
            services.register_payment(self.draft(), date(2026, 11, 20), D('10'), 'USD')

    def test_vat_withholding_75(self):
        inv = self.issued()
        ret = services.register_vat_withholding(inv, '20261100000001', date(2026, 11, 10), user=self.user)
        self.assertEqual((ret.percent, ret.amount, ret.amount_ves), (75, D('50.25'), D('20100.00')))
        inv.refresh_from_db()
        self.assertEqual(inv.balance_due, D('396.75'))
        self.assertEqual(self.obligation('iva'), D('6700.00'))  # 26.800 - 20.100
        with self.assertRaises(services.InvoiceError):
            services.register_vat_withholding(inv, '20261100000002', date(2026, 11, 10))
        self.assert_books_balance()


class NotesAndVoidTests(SalesBase):

    def test_credit_note_reduces_balance_and_vat(self):
        inv = self.issued()
        note = self.issued(doc_type='credit_note', related=inv, lines=[(1, '100', 'general')])
        inv.refresh_from_db()
        self.assertEqual((note.total, inv.credited, inv.balance_due, inv.status),
                         (D('116'), D('116'), D('331'), 'partial'))
        self.assertEqual(self.obligation('iva'), D('20400.00'))  # 26.800 - 16 x 400
        self.assert_books_balance()

    def test_credit_note_cannot_exceed_balance(self):
        inv = self.issued()
        with self.assertRaisesMessage(services.InvoiceError, 'supera el saldo'):
            self.issued(doc_type='credit_note', related=inv, lines=[(1, '1000', 'general')])

    def test_note_requires_issued_invoice_of_same_customer(self):
        with self.assertRaises(services.InvoiceError):
            self.issued(doc_type='credit_note', related=self.draft(), lines=[(1, '10', 'general')])

    def test_debit_note_adds_receivable(self):
        inv = self.issued()
        note = self.issued(doc_type='debit_note', related=inv, lines=[(1, '10', 'general')])
        self.assertEqual((note.balance_due, note.status), (D('11.60'), 'issued'))
        self.assert_books_balance()

    def test_void_keeps_number_reverses_entry_and_clears_vat(self):
        inv = self.issued()
        services.void_invoice(inv, 'Error en datos del cliente', self.user)
        inv.refresh_from_db()
        self.assertEqual((inv.status, inv.number, inv.balance_due), ('void', '00000001', D('0')))
        self.assertIsNone(self.obligation('iva'))
        book = services.sales_book(self.tenant, 2026, 11)
        self.assertEqual(book['rows'][0]['status'], 'ANULADA')
        self.assertEqual(book['totals']['total'], D('0'))
        self.assert_books_balance()

    def test_void_restrictions(self):
        inv = self.issued()
        services.register_payment(inv, date(2026, 11, 20), D('10'), 'USD')
        with self.assertRaisesMessage(services.InvoiceError, 'nota de credito'):
            services.void_invoice(inv, 'x')
        with self.assertRaises(services.InvoiceError):
            services.void_invoice(self.draft(), 'x')
        with self.assertRaises(services.InvoiceError):
            services.void_invoice(self.issued(), '')

    def test_voiding_credit_note_restores_invoice_balance(self):
        inv = self.issued()
        note = self.issued(doc_type='credit_note', related=inv, lines=[(1, '100', 'general')])
        services.void_invoice(note, 'Nota emitida por error')
        inv.refresh_from_db()
        self.assertEqual((inv.balance_due, inv.credited, inv.status), (D('447'), D('0'), 'issued'))


class SalesBookTests(SalesBase):

    def test_book_in_bolivares_with_credit_notes_negative(self):
        inv = self.issued()
        self.issued(doc_type='credit_note', related=inv, lines=[(1, '100', 'general')])
        services.register_vat_withholding(inv, '20261100000001', date(2026, 11, 10))
        book = services.sales_book(self.tenant, 2026, 11)
        first, note = book['rows']
        self.assertEqual((first['total'], first['tax_general'], first['vat_withheld']),
                         (D('178800.00'), D('12800.00'), D('20100.00')))
        self.assertEqual((note['total'], note['affected_invoice']), (D('-46400.00'), '00000001'))
        self.assertEqual(book['totals']['tax_total'], D('20400.00'))


class SalesApiTests(SalesBase):

    def setUp(self):
        super().setUp()
        self.manager = User.objects.create_user('gerente', password='x')
        UserTenantRole.objects.create(tenant=self.tenant, user=self.manager, role='manager')
        self.api = APIClient()
        self.api.force_authenticate(self.manager)
        self.url = '/api/finance/sales/invoices/'

    def payload(self, **overrides):
        line = {'description': 'Servicio', 'quantity': '1', 'unit_price': '100.00', 'tax_category': 'general'}
        data = {'tenant': self.tenant.id, 'customer': self.customer.id, 'issue_date': '2026-11-05',
                'currency': 'usd', 'lines': [line]}
        data.update(overrides)
        return data

    def test_full_flow(self):
        created = self.api.post(self.url, self.payload(), format='json')
        self.assertEqual(created.status_code, 201, created.data)
        self.assertEqual((created.data['currency'], created.data['total']), ('USD', '116.00'))
        pk = created.data['id']
        issued = self.api.post(f'{self.url}{pk}/issue/')
        self.assertEqual(issued.status_code, 200, issued.data)
        self.assertEqual(issued.data['total_ves'], D('46400.00'))
        self.assertEqual(self.api.patch(f'{self.url}{pk}/', {'notes': 'x'}, format='json').status_code, 400)
        self.assertEqual(self.api.delete(f'{self.url}{pk}/').status_code, 400)
        paid = self.api.post(f'{self.url}{pk}/pay/', {'payment_date': '2026-11-20', 'amount': '116',
                                                      'currency': 'USD', 'method': 'zelle'})
        self.assertEqual(paid.status_code, 201, paid.data)
        self.assertEqual(paid.data['igtf_amount'], '3.48')
        again = self.api.post(f'{self.url}{pk}/pay/', {'payment_date': '2026-11-20', 'amount': '1', 'currency': 'USD'})
        self.assertEqual(again.status_code, 400)

    def test_draft_can_be_edited_and_deleted(self):
        pk = self.api.post(self.url, self.payload(), format='json').data['id']
        response = self.api.patch(f'{self.url}{pk}/', {'lines': [
            {'description': 'Otro', 'quantity': '2', 'unit_price': '10.00', 'tax_category': 'exempt'}]},
            format='json')
        self.assertEqual((response.status_code, response.data['total']), (200, '20.00'))
        self.assertEqual(self.api.delete(f'{self.url}{pk}/').status_code, 204)

    def test_customer_of_other_company_rejected(self):
        other = Tenant.objects.create(name='Otra', slug='otra')
        foreign = Customer.objects.create(tenant=other, rif='V-12345678-1', name='Ajeno')
        response = self.api.post(self.url, self.payload(customer=foreign.id), format='json')
        self.assertEqual(response.status_code, 400)

    def test_invalid_rif_rejected(self):
        response = self.api.post('/api/finance/sales/customers/', {
            'tenant': self.tenant.id, 'rif': '12345', 'name': 'Sin RIF'})
        self.assertEqual(response.status_code, 400)

    def test_other_company_cannot_see_invoices(self):
        self.issued()
        outsider = User.objects.create_user('otro', password='x')
        other = Tenant.objects.create(name='Otra', slug='otra')
        UserTenantRole.objects.create(tenant=other, user=outsider, role='manager')
        client = APIClient()
        client.force_authenticate(outsider)
        self.assertEqual(client.get(self.url).data['count'], 0)
        response = client.get(f'/api/finance/sales/sales-book/?tenant_id={self.tenant.id}&year=2026&month=11')
        self.assertEqual(response.status_code, 403)

    def test_sales_book_csv(self):
        self.issued()
        response = self.api.get(
            f'/api/finance/sales/sales-book/?tenant_id={self.tenant.id}&year=2026&month=11&export=csv')
        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8-sig')
        self.assertIn('N° de control', content)
        self.assertIn('00-00000001', content)
        self.assertIn('178800,00', content)
        self.assertIn('05/11/2026', content)
