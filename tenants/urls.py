from rest_framework.routers import DefaultRouter

from .views import TenantSettingViewSet, TenantViewSet

router = DefaultRouter()
# 'settings' va primero: con el prefijo vacio, '/settings/' se tomaria como el detalle de una empresa.
router.register('settings', TenantSettingViewSet, basename='tenant-setting')
router.register('', TenantViewSet, basename='tenant')

urlpatterns = router.urls
