from celery import shared_task

from .services import BCVError, update_bcv_rates


@shared_task(bind=True, max_retries=6, default_retry_delay=30 * 60)
def update_bcv_rates_task(self):
    """Descarga la tasa oficial del BCV; reintenta cada 30 minutos si falla."""
    try:
        bcv_rates, count = update_bcv_rates()
    except BCVError as exc:
        raise self.retry(exc=exc)
    return {'fecha_valor': str(bcv_rates.value_date), 'registros': count}
