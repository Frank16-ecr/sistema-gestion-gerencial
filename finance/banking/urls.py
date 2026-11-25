from rest_framework.routers import DefaultRouter

from .views import BankAccountViewSet, BankReconciliationViewSet, ChequeViewSet, PettyCashTransactionViewSet

router = DefaultRouter()
router.register('bank-accounts', BankAccountViewSet, basename='bank-account')
router.register('reconciliations', BankReconciliationViewSet, basename='bank-reconciliation')
router.register('petty-cash', PettyCashTransactionViewSet, basename='petty-cash')
router.register('cheques', ChequeViewSet, basename='cheque')

urlpatterns = router.urls
