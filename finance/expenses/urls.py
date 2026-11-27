from rest_framework.routers import DefaultRouter

from .views import ExpenseViewSet, ReimbursementBatchViewSet, ReimbursementRequestViewSet

router = DefaultRouter()
router.register('expenses', ExpenseViewSet, basename='expense')
router.register('reimbursement-batches', ReimbursementBatchViewSet, basename='reimbursement-batch')
router.register('reimbursement-requests', ReimbursementRequestViewSet, basename='reimbursement-request')

urlpatterns = router.urls
