from django.contrib import admin
from django.urls import path, include
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
    path('api/tenants/', include('tenants.urls')),
    path('api/finance/accounts/', include('finance.accounts.urls')),
    path('api/finance/invoicing/', include('finance.invoicing.urls')),
    path('api/finance/payments/', include('finance.payments.urls')),
    path('api/finance/expenses/', include('finance.expenses.urls')),
    path('api/finance/payroll/', include('finance.payroll.urls')),
    path('api/finance/statutory/', include('finance.statutory.urls')),
    path('api/finance/banking/', include('finance.banking.urls')),
    path('api/finance/fx/', include('finance.fx.urls')),
    path('api/finance/audit/', include('finance.audit.urls')),
    path('api/finance/reports/', include('finance.reports.urls')),
]
