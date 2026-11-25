from django.urls import path

from rest_framework.routers import DefaultRouter

from .views import (
    CustomerViewSet, InvoicePaymentViewSet, InvoiceViewSet, SalesBookView, TaxpayerProfileViewSet,
    VatWithholdingViewSet,
)

router = DefaultRouter()
router.register('taxpayer-profiles', TaxpayerProfileViewSet, basename='taxpayer-profile')
router.register('customers', CustomerViewSet, basename='customer')
router.register('invoices', InvoiceViewSet, basename='sales-invoice')
router.register('payments', InvoicePaymentViewSet, basename='sales-payment')
router.register('vat-withholdings', VatWithholdingViewSet, basename='vat-withholding')

urlpatterns = [
    path('sales-book/', SalesBookView.as_view(), name='sales-book'),
] + router.urls
