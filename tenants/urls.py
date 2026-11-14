from rest_framework.routers import DefaultRouter
from .views import TenantViewSet, TenantSettingViewSet

router = DefaultRouter()
router.register('', TenantViewSet, basename='tenant')
router.register('settings', TenantSettingViewSet, basename='tenant-setting')

urlpatterns = router.urls
