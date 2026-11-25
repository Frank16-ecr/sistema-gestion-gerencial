from django.contrib import admin

from .models import FeeNote, FeeNoteReminder


@admin.register(FeeNote)
class FeeNoteAdmin(admin.ModelAdmin):
    list_display = (
        'fee_note_number', 'tenant', 'insurer_name', 'total_amount', 'invoice_currency', 'status', 'due_date',
        'created_at',
    )
    search_fields = ('fee_note_number', 'insurer_name', 'efris_fiscal_number')
    list_filter = ('status', 'is_void', 'invoice_currency', 'tenant')
    date_hierarchy = 'created_at'


@admin.register(FeeNoteReminder)
class FeeNoteReminderAdmin(admin.ModelAdmin):
    list_display = ('fee_note', 'reminder_type', 'sent_to', 'success', 'sent_at')
    search_fields = ('fee_note__fee_note_number', 'sent_to')
    list_filter = ('reminder_type', 'success')
