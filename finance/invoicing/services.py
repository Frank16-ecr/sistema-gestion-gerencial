import logging
from datetime import date, timedelta
from django.utils import timezone

logger = logging.getLogger(__name__)


class FeeNoteService:

    @staticmethod
    def generate_from_claim(claim_data, tenant, user):
        """Creates a FeeNote from claim data, posts journal entries, queues EFRIS submission."""
        from finance.invoicing.models import FeeNote
        from finance.accounts.models import JournalEntry, JournalLine, Account

        from decimal import Decimal
        fee_note_number = claim_data.get('fee_note_number', f"FN-{timezone.now().strftime('%Y%m%d%H%M%S')}")
        invoice_amount = Decimal(str(claim_data.get('invoice_amount', 0)))
        vat_amount = Decimal(str(claim_data.get('vat_amount', 0)))
        total_amount = invoice_amount + vat_amount
        exchange_rate = Decimal(str(claim_data.get('exchange_rate', 1)))
        base_currency_amount = total_amount * exchange_rate

        fee_note = FeeNote.objects.create(
            tenant=tenant,
            claim_id=claim_data['claim_id'],
            fee_note_number=fee_note_number,
            insurer_id=claim_data['insurer_id'],
            insurer_name=claim_data.get('insurer_name', ''),
            insurer_email=claim_data.get('insurer_email', ''),
            invoice_currency=claim_data.get('invoice_currency', 'UGX'),
            invoice_amount=invoice_amount,
            vat_amount=vat_amount,
            total_amount=total_amount,
            exchange_rate_at_issue=exchange_rate,
            base_currency_amount=base_currency_amount,
            ugx_amount_efris=base_currency_amount,
            balance_due=total_amount,
            due_date=claim_data.get('due_date'),
            created_by=user,
            status='draft',
        )

        logger.info("FeeNote %s created for claim %s", fee_note.fee_note_number, fee_note.claim_id)

        # Queue EFRIS submission as a background task
        try:
            from zelani.celery import app as celery_app
            celery_app.send_task('finance.invoicing.tasks.submit_fee_note_to_efris', args=[fee_note.pk])
        except Exception as e:
            logger.warning("Could not queue EFRIS submission: %s", e)

        return fee_note

    @staticmethod
    def submit_to_efris(fee_note):
        """Stub: Submit fee note to EFRIS."""
        logger.info("Submitting FeeNote %s to EFRIS (stub)", fee_note.fee_note_number)
        fee_note.status = 'submitted'
        fee_note.save(update_fields=['status'])

    @staticmethod
    def send_to_insurer(fee_note, user):
        """Stub: Send email to insurer."""
        logger.info(
            "Sending FeeNote %s to insurer %s (stub)",
            fee_note.fee_note_number,
            fee_note.insurer_email,
        )
        fee_note.status = 'sent'
        fee_note.sent_at = timezone.now()
        fee_note.save(update_fields=['status', 'sent_at'])

    @staticmethod
    def void_fee_note(fee_note, reason, user):
        """Voids a fee note."""
        fee_note.is_void = True
        fee_note.void_reason = reason
        fee_note.voided_by = user
        fee_note.voided_at = timezone.now()
        fee_note.status = 'void'
        fee_note.save(update_fields=['is_void', 'void_reason', 'voided_by', 'voided_at', 'status'])
        logger.info("FeeNote %s voided by %s: %s", fee_note.fee_note_number, user, reason)

    @staticmethod
    def update_overdue_statuses(tenant):
        """Updates fee note statuses based on due dates."""
        from finance.invoicing.models import FeeNote
        today = date.today()
        active_statuses = ['sent', 'partial', 'overdue_1', 'overdue_2']
        notes = FeeNote.objects.filter(tenant=tenant, is_void=False, status__in=active_statuses)

        for fn in notes:
            if fn.due_date is None:
                continue
            days_overdue = (today - fn.due_date).days
            if days_overdue >= 90:
                new_status = 'overdue_3'
            elif days_overdue >= 60:
                new_status = 'overdue_2'
            elif days_overdue >= 30:
                new_status = 'overdue_1'
            else:
                continue
            if fn.status != new_status:
                fn.status = new_status
                fn.save(update_fields=['status'])
                logger.info("FeeNote %s status updated to %s", fn.fee_note_number, new_status)
