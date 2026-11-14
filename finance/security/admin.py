from django.contrib import admin

from .models import UserTenantRole


@admin.register(UserTenantRole)
class UserTenantRoleAdmin(admin.ModelAdmin):
    list_display = ('user', 'tenant', 'role', 'is_active', 'assigned_by', 'created_at')
    list_filter = ('role', 'is_active', 'tenant')
    search_fields = ('user__username', 'user__email')
