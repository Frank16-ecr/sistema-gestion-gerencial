from rest_framework.routers import DefaultRouter

from .views import FeeNoteReminderViewSet, FeeNoteViewSet

router = DefaultRouter()
router.register('fee-notes', FeeNoteViewSet, basename='fee-note')
router.register('reminders', FeeNoteReminderViewSet, basename='fee-note-reminder')

urlpatterns = router.urls
