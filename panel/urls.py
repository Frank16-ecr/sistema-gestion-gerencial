from django.contrib.auth import views as auth_views
from django.urls import path

from . import views, views_accounting, views_billing, views_payroll, views_treasury

app_name = 'panel'

urlpatterns = [
    path('', views.home, name='home'),
    path('login/', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),

    path('presupuestos/', views.budget_list, name='budgets'),
    path('presupuestos/nuevo/', views.budget_create, name='budget-create'),
    path('presupuestos/<int:pk>/', views.budget_detail, name='budget-detail'),
    path('presupuestos/<int:pk>/editar/', views.budget_edit, name='budget-edit'),
    path('presupuestos/<int:pk>/<slug:action>/', views.budget_action, name='budget-action'),

    path('gastos/', views.expense_list, name='expenses'),
    path('gastos/nuevo/', views.expense_create, name='expense-create'),
    path('gastos/<int:pk>/<slug:action>/', views.expense_action, name='expense-action'),

    path('inversiones/', views.investment_list, name='investments'),
    path('inversiones/nueva/', views.investment_create, name='investment-create'),
    path('inversiones/<int:pk>/', views.investment_detail, name='investment-detail'),
    path('inversiones/<int:pk>/editar/', views.investment_edit, name='investment-edit'),
    path('inversiones/<int:pk>/eliminar/', views.investment_delete, name='investment-delete'),
    path('inversiones/<int:pk>/movimientos/', views.movement_add, name='movement-add'),
    path('inversiones/<int:pk>/movimientos/<int:movement_pk>/eliminar/', views.movement_delete,
         name='movement-delete'),

    path('cobros/notas/', views_billing.invoice_list, name='invoices'),
    path('cobros/notas/nueva/', views_billing.invoice_create, name='invoice-create'),
    path('cobros/notas/actualizar-vencidas/', views_billing.invoice_refresh, name='invoice-refresh'),
    path('cobros/notas/<int:pk>/', views_billing.invoice_detail, name='invoice-detail'),
    path('cobros/notas/<int:pk>/editar/', views_billing.invoice_edit, name='invoice-edit'),
    path('cobros/notas/<int:pk>/pago/', views_billing.payment_create, name='payment-create'),
    path('cobros/notas/<int:pk>/recordatorio/', views_billing.reminder_create, name='reminder-create'),
    path('cobros/notas/<int:pk>/<slug:action>/', views_billing.invoice_action, name='invoice-action'),
    path('cobros/pagos/', views_billing.payment_list, name='payments'),
    path('cobros/retenciones/', views_billing.wht_list, name='wht'),
    path('cobros/retenciones/<int:pk>/alternar/', views_billing.wht_toggle, name='wht-toggle'),

    path('nomina/empleados/', views_payroll.employee_list, name='employees'),
    path('nomina/empleados/nuevo/', views_payroll.employee_create, name='employee-create'),
    path('nomina/empleados/<int:pk>/', views_payroll.employee_detail, name='employee-detail'),
    path('nomina/empleados/<int:pk>/editar/', views_payroll.employee_edit, name='employee-edit'),
    path('nomina/empleados/<int:pk>/complementos/', views_payroll.allowance_add, name='allowance-add'),
    path('nomina/complementos/<int:pk>/alternar/', views_payroll.allowance_toggle, name='allowance-toggle'),
    path('nomina/complementos/<int:pk>/eliminar/', views_payroll.allowance_delete, name='allowance-delete'),
    path('nomina/corridas/', views_payroll.payroll_list, name='payroll'),
    path('nomina/corridas/calcular/', views_payroll.payroll_create, name='payroll-create'),
    path('nomina/corridas/<int:pk>/', views_payroll.payroll_detail, name='payroll-detail'),
    path('nomina/corridas/<int:pk>/<slug:action>/', views_payroll.payroll_action, name='payroll-action'),

    path('tesoreria/cuentas/', views_treasury.bank_account_list, name='bank-accounts'),
    path('tesoreria/cuentas/nueva/', views_treasury.bank_account_create, name='bank-account-create'),
    path('tesoreria/cuentas/<int:pk>/editar/', views_treasury.bank_account_edit, name='bank-account-edit'),
    path('tesoreria/conciliaciones/', views_treasury.reconciliation_list, name='reconciliations'),
    path('tesoreria/conciliaciones/nueva/', views_treasury.reconciliation_create, name='reconciliation-create'),
    path('tesoreria/conciliaciones/<int:pk>/', views_treasury.reconciliation_detail, name='reconciliation-detail'),
    path('tesoreria/conciliaciones/<int:pk>/cerrar/', views_treasury.reconciliation_lock, name='reconciliation-lock'),
    path('tesoreria/caja-chica/', views_treasury.petty_cash_list, name='petty-cash'),
    path('tesoreria/caja-chica/nuevo/', views_treasury.petty_cash_create, name='petty-cash-create'),
    path('tesoreria/cheques/', views_treasury.cheque_list, name='cheques'),
    path('tesoreria/cheques/nuevo/', views_treasury.cheque_create, name='cheque-create'),
    path('tesoreria/cheques/<int:pk>/<slug:action>/', views_treasury.cheque_action, name='cheque-action'),

    path('contabilidad/cuentas/', views_accounting.account_list, name='chart-of-accounts'),
    path('contabilidad/cuentas/nueva/', views_accounting.account_create, name='account-create'),
    path('contabilidad/cuentas/<int:pk>/editar/', views_accounting.account_edit, name='account-edit'),
    path('contabilidad/asientos/', views_accounting.journal_list, name='journal'),
    path('contabilidad/asientos/nuevo/', views_accounting.journal_create, name='journal-create'),
    path('contabilidad/asientos/<int:pk>/', views_accounting.journal_detail, name='journal-detail'),
    path('contabilidad/asientos/<int:pk>/anular/', views_accounting.journal_void, name='journal-void'),
    path('contabilidad/reportes/', views_accounting.reports, name='reports'),
]
