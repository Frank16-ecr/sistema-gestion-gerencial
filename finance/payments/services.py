import logging
from decimal import Decimal

logger = logging.getLogger(__name__)


class PaymentService:

    @staticmethod
    def calculate_fx_gain_loss(fee_note, payment):
        """
        Calculate FX gain/loss.
        FX gain/loss = (payment exchange rate - fee note issue rate) * foreign amount received
        """
        from tenants.config import base_currency

        if fee_note.invoice_currency == base_currency(fee_note.tenant):
            return Decimal('0.00')
        rate_diff = payment.exchange_rate - fee_note.exchange_rate_at_issue
        fx_gain_loss = rate_diff * payment.amount_received_foreign
        return fx_gain_loss

    @staticmethod
    def record_payment(fee_note, payload, user):
        """
        Records payment, calculates FX gain/loss, WHT credit,
        updates invoice status, posts journals.
        """
        from finance.payments.models import FeeNotePayment, WHTCredit

        amount_received_foreign = Decimal(str(payload['amount_received_foreign']))
        exchange_rate = Decimal(str(payload.get('exchange_rate', 1)))
        base_currency_received = amount_received_foreign * exchange_rate

        payment = FeeNotePayment(
            tenant=fee_note.tenant,
            fee_note=fee_note,
            payment_currency=payload.get('payment_currency', fee_note.invoice_currency),
            amount_received_foreign=amount_received_foreign,
            exchange_rate=exchange_rate,
            base_currency_received=base_currency_received,
            payment_date=payload['payment_date'],
            payment_method=payload.get('payment_method', 'bank_transfer'),
            bank_reference=payload.get('bank_reference', ''),
            wht_deducted=payload.get('wht_deducted', False),
            wht_amount=Decimal(str(payload.get('wht_amount', 0))),
            wht_cert_number=payload.get('wht_cert_number', ''),
            efris_receipt_ref=payload.get('efris_receipt_ref', ''),
            recorded_by=user,
        )

        fx_gain_loss = PaymentService.calculate_fx_gain_loss(fee_note, payment)
        payment.fx_gain_loss = fx_gain_loss
        payment.save()

        # Update fee note balances
        fee_note.amount_paid = (fee_note.amount_paid or Decimal('0')) + amount_received_foreign
        fee_note.balance_due = fee_note.total_amount - fee_note.amount_paid
        if fee_note.balance_due <= 0:
            fee_note.status = 'paid'
        elif fee_note.amount_paid > 0:
            fee_note.status = 'partial'
        fee_note.save(update_fields=['amount_paid', 'balance_due', 'status'])

        # Create WHT credit if applicable
        if payment.wht_deducted and payment.wht_amount > 0:
            payment_date = payload['payment_date']
            if hasattr(payment_date, 'year'):
                year = payment_date.year
                month = payment_date.month
            else:
                from datetime import date
                d = date.fromisoformat(str(payment_date))
                year = d.year
                month = d.month

            WHTCredit.objects.create(
                tenant=fee_note.tenant,
                payment=payment,
                amount=payment.wht_amount,
                cert_number=payment.wht_cert_number,
                period_year=year,
                period_month=month,
            )

        logger.info(
            "Payment recorded for FeeNote %s: %s %s (FX gain/loss: %s)",
            fee_note.fee_note_number,
            payment.payment_currency,
            payment.amount_received_foreign,
            fx_gain_loss,
        )
        return payment
