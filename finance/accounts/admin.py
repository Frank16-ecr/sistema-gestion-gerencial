from django.contrib import admin

from .models import Account, JournalEntry, JournalLine


@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'category', 'tenant', 'is_active', 'created_at')
    search_fields = ('code', 'name')
    list_filter = ('category', 'is_active', 'tenant')


class JournalLineInline(admin.TabularInline):
    model = JournalLine
    extra = 0


@admin.register(JournalEntry)
class JournalEntryAdmin(admin.ModelAdmin):
    list_display = ('pk', 'tenant', 'entry_date', 'reference', 'is_void', 'created_at')
    search_fields = ('reference', 'description')
    list_filter = ('is_void', 'tenant', 'entry_date')
    inlines = [JournalLineInline]


@admin.register(JournalLine)
class JournalLineAdmin(admin.ModelAdmin):
    list_display = ('journal_entry', 'account', 'debit_amount', 'credit_amount', 'tenant')
    search_fields = ('account__name', 'description')
    list_filter = ('tenant',)
