from rest_framework.routers import DefaultRouter

from .views import InvestmentMovementViewSet, InvestmentViewSet

router = DefaultRouter()
router.register('investments', InvestmentViewSet, basename='investment')
router.register('movements', InvestmentMovementViewSet, basename='investment-movement')

urlpatterns = router.urls
