from rest_framework.routers import DefaultRouter

from .views import UserTenantRoleViewSet

router = DefaultRouter()
router.register('roles', UserTenantRoleViewSet, basename='tenant-role')

urlpatterns = router.urls
