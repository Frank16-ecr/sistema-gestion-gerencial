from django.contrib import admin

from .models import Tenant, TenantSetting


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'is_active', 'created_at')
    search_fields = ('name', 'slug')
    list_filter = ('is_active',)
    prepopulated_fields = {'slug': ('name',)}


@admin.register(TenantSetting)
class TenantSettingAdmin(admin.ModelAdmin):
    list_display = ('tenant', 'setting_key', 'updated_at')
    search_fields = ('tenant__name', 'setting_key')
    list_filter = ('tenant',)
