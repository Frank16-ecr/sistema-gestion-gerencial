from rest_framework.routers import DefaultRouter
from .views import (
    EmployeePayrollProfileViewSet, EmployeeAllowanceViewSet,
    PayrollRunViewSet, PayrollLineViewSet,
)

router = DefaultRouter()
router.register('employee-profiles', EmployeePayrollProfileViewSet, basename='employee-profile')
router.register('allowances', EmployeeAllowanceViewSet, basename='employee-allowance')
router.register('runs', PayrollRunViewSet, basename='payroll-run')
router.register('lines', PayrollLineViewSet, basename='payroll-line')

urlpatterns = router.urls
