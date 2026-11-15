from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

app_name = 'panel'

urlpatterns = [
    path('', views.home, name='home'),
    path('login/', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('presupuestos/', views.budget_list, name='budgets'),
    path('presupuestos/<int:pk>/', views.budget_detail, name='budget-detail'),
    path('inversiones/', views.investment_list, name='investments'),
    path('inversiones/<int:pk>/', views.investment_detail, name='investment-detail'),
]
