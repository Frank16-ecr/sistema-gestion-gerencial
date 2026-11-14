from rest_framework.routers import DefaultRouter
from .views import AccountViewSet, JournalEntryViewSet, JournalLineViewSet

router = DefaultRouter()
router.register('chart-of-accounts', AccountViewSet, basename='account')
router.register('journal-entries', JournalEntryViewSet, basename='journal-entry')
router.register('journal-lines', JournalLineViewSet, basename='journal-line')

urlpatterns = router.urls
