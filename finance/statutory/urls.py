from rest_framework.routers import DefaultRouter

from .views import StatutoryObligationViewSet

router = DefaultRouter()
router.register('obligations', StatutoryObligationViewSet, basename='statutory-obligation')

urlpatterns = router.urls
