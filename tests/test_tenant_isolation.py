"""Aislamiento entre empresas en los modulos originales (antes solo exigian login)."""
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model

from finance.accounts.models import Account
from finance.audit.models import AuditLog
from finance.expenses.models import Expense
from finance.payroll.models import EmployeeAllowance, EmployeePayrollProfile
from finance.security.models import UserTenantRole
from tenants.models import TenantSetting

from .test_management_modules import ManagementTestBase

User = get_user_model()

BASE = '/api/finance'


class IsolationBase(ManagementTestBase):

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.auditor = User.objects.create_user('auditor', password='pass12345')
        UserTenantRole.objects.create(tenant=cls.tenant1, user=cls.auditor, role='auditor')
        cls.expense1 = Expense.objects.create(
            tenant=cls.tenant1, description='Alquiler uno', category='rent', amount=Decimal('100'),
            currency='USD', expense_date=date(2026, 3, 1),
        )
        cls.expense2 = Expense.objects.create(
            tenant=cls.tenant2, description='Alquiler dos', category='rent', amount=Decimal('200'),
            currency='USD', expense_date=date(2026, 3, 1),
        )


class ListScopingTests(IsolationBase):

    def ids(self, response):
        self.assertEqual(response.status_code, 200)
        return {row['id'] for row in response.data['results']}

    def test_lists_only_show_own_tenant(self):
        Account.objects.create(tenant=self.tenant1, code='1000', name='Caja', category='asset')
        Account.objects.create(tenant=self.tenant2, code='1000', name='Caja', category='asset')
        for url in (f'{BASE}/expenses/expenses/', f'{BASE}/accounts/chart-of-accounts/'):
            with self.subTest(url=url):
                rows = self.client_for(self.viewer).get(url).data['results']
                self.assertTrue(rows)
                self.assertEqual({r['tenant'] for r in rows}, {self.tenant1.id})

    def test_superuser_sees_everything(self):
        ids = self.ids(self.client_for(self.admin).get(f'{BASE}/expenses/expenses/'))
        self.assertEqual(ids, {self.expense1.id, self.expense2.id})

    def test_user_without_roles_is_rejected(self):
        self.assertEqual(self.client_for(self.outsider).get(f'{BASE}/expenses/expenses/').status_code, 403)

    def test_other_tenant_detail_is_not_found(self):
        url = f'{BASE}/expenses/expenses/{self.expense2.id}/'
        self.assertEqual(self.client_for(self.manager).get(url).status_code, 404)

    def test_tenants_endpoint_lists_only_own_companies(self):
        rows = self.client_for(self.viewer).get('/api/tenants/').data['results']
        self.assertEqual([r['id'] for r in rows], [self.tenant1.id])


class WriteRulesTests(IsolationBase):
    url = f'{BASE}/expenses/expenses/'

    def payload(self, **overrides):
        data = {'tenant': self.tenant1.id, 'description': 'Internet', 'category': 'internet',
                'amount': '50.00', 'currency': 'USD', 'expense_date': '2026-03-05'}
        data.update(overrides)
        return data

    def test_manager_creates_in_own_tenant_and_is_recorded_as_submitter(self):
        response = self.client_for(self.manager).post(self.url, self.payload(), format='json')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Expense.objects.get(pk=response.data['id']).submitted_by, self.manager)

    def test_manager_cannot_create_in_other_tenant(self):
        response = self.client_for(self.manager).post(self.url, self.payload(tenant=self.tenant2.id), format='json')
        self.assertEqual(response.status_code, 403)

    def test_manager_cannot_move_record_to_other_tenant(self):
        response = self.client_for(self.manager).patch(
            f'{self.url}{self.expense1.id}/', {'tenant': self.tenant2.id}, format='json')
        self.assertEqual(response.status_code, 403)
        self.expense1.refresh_from_db()
        self.assertEqual(self.expense1.tenant, self.tenant1)

    def test_viewer_cannot_write(self):
        self.assertEqual(self.client_for(self.viewer).post(self.url, self.payload(), format='json').status_code, 403)

    def test_only_superuser_creates_tenants(self):
        data = {'name': 'Nueva', 'slug': 'nueva'}
        self.assertEqual(self.client_for(self.manager).post('/api/tenants/', data).status_code, 403)
        self.assertEqual(self.client_for(self.admin).post('/api/tenants/', data).status_code, 201)

    def test_tenant_settings_require_admin_role(self):
        data = {'tenant': self.tenant1.id, 'setting_key': 'base_currency', 'setting_value': 'EUR'}
        url = '/api/tenants/settings/'
        self.assertEqual(self.client_for(self.manager).post(url, data, format='json').status_code, 403)
        UserTenantRole.objects.filter(user=self.manager).update(role='admin')
        self.assertEqual(self.client_for(self.manager).post(url, data, format='json').status_code, 201)


class SensitiveDataTests(IsolationBase):

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.employee = EmployeePayrollProfile.objects.create(
            tenant=cls.tenant1, user=cls.viewer, employee_number='E1',
            gross_salary=Decimal('1000000'), start_date=date(2026, 1, 1),
        )
        EmployeeAllowance.objects.create(employee=cls.employee, allowance_type='transport', amount=Decimal('5'))

    def test_viewer_cannot_see_salaries(self):
        for url in (f'{BASE}/payroll/employee-profiles/', f'{BASE}/payroll/allowances/'):
            with self.subTest(url=url):
                self.assertEqual(self.client_for(self.viewer).get(url).status_code, 403)

    def test_auditor_reads_payroll_but_cannot_write(self):
        client = self.client_for(self.auditor)
        self.assertEqual(client.get(f'{BASE}/payroll/allowances/').data['count'], 1)
        response = client.post(f'{BASE}/payroll/allowances/', {
            'employee': self.employee.id, 'allowance_type': 'lunch', 'amount': '10.00'}, format='json')
        self.assertEqual(response.status_code, 403)

    def test_allowance_scoped_through_employee(self):
        self.assertEqual(self.client_for(self.admin).get(f'{BASE}/payroll/allowances/').data['count'], 1)
        UserTenantRole.objects.create(tenant=self.tenant2, user=self.outsider, role='manager')
        self.assertEqual(self.client_for(self.outsider).get(f'{BASE}/payroll/allowances/').data['count'], 0)

    def test_run_monthly_checks_tenant_access(self):
        url = f'{BASE}/payroll/runs/run_monthly/'
        client = self.client_for(self.manager)
        self.assertEqual(client.post(url, {'tenant_id': self.tenant2.id, 'month': 1, 'year': 2026}).status_code, 403)
        self.assertEqual(client.post(url, {'tenant_id': self.tenant1.id, 'month': 13, 'year': 2026}).status_code, 400)
        self.assertEqual(client.post(url, {'tenant_id': 'x'}).status_code, 400)
        self.assertEqual(client.post(url, {'tenant_id': self.tenant1.id, 'month': 1, 'year': 2026}).status_code, 200)

    def test_audit_log_hidden_from_viewers(self):
        AuditLog.objects.create(tenant=self.tenant1, action='create', model_name='Expense', object_id='1')
        url = f'{BASE}/audit/logs/'
        self.assertEqual(self.client_for(self.viewer).get(url).status_code, 403)
        self.assertEqual(self.client_for(self.auditor).get(url).data['count'], 1)

    def test_tenant_setting_of_other_company_is_hidden(self):
        TenantSetting.objects.create(tenant=self.tenant2, setting_key='base_currency', setting_value='EUR')
        self.assertEqual(self.client_for(self.manager).get('/api/tenants/settings/').data['count'], 0)
