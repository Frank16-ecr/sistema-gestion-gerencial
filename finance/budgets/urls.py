from rest_framework.routers import DefaultRouter

from .views import BudgetLineViewSet, BudgetViewSet

router = DefaultRouter()
router.register('budgets', BudgetViewSet, basename='budget')
router.register('lines', BudgetLineViewSet, basename='budget-line')

urlpatterns = router.urls
