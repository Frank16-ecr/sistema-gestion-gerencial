from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

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
]
