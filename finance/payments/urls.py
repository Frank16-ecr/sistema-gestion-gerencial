from rest_framework.routers import DefaultRouter
from .views import FeeNotePaymentViewSet, WHTCreditViewSet

router = DefaultRouter()
router.register('fee-note-payments', FeeNotePaymentViewSet, basename='fee-note-payment')
router.register('wht-credits', WHTCreditViewSet, basename='wht-credit')

urlpatterns = router.urls
