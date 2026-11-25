"""Tipos de cambio: consulta por fecha y descarga de la tasa oficial del BCV.

En Venezuela la tasa oficial publicada por el Banco Central de Venezuela (BCV)
es la referencia para expresar en bolivares las operaciones en divisas
(facturas, pagos, IGTF, nomina). El BCV publica la tasa con una "fecha valor",
normalmente el dia habil siguiente.
"""
import logging
import re
import ssl
import urllib.request
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.db import transaction

logger = logging.getLogger(__name__)

BCV_SOURCE = 'bcv'
# id del bloque HTML en la portada del BCV -> codigo ISO de la moneda
BCV_CURRENCY_BLOCKS = {'dolar': 'USD', 'euro': 'EUR', 'yuan': 'CNY', 'lira': 'TRY', 'rublo': 'RUB'}


class ExchangeRateNotFound(LookupError):
    """No hay tasa registrada para la moneda y fecha pedidas."""


class BCVError(RuntimeError):
    """No se pudo obtener o interpretar la tasa del BCV."""


@dataclass
class BCVRates:
    value_date: date
    rates: dict  # {'USD': Decimal(...), ...}


def get_rate(tenant, from_currency, to_currency, on_date):
    """Tasa vigente para la fecha: la ultima publicada en o antes de `on_date`."""
    from .models import ExchangeRate

    if from_currency == to_currency:
        return Decimal('1')
    row = (
        ExchangeRate.objects.filter(
            tenant=tenant, from_currency=from_currency, to_currency=to_currency, rate_date__lte=on_date,
        )
        .order_by('-rate_date', '-id')
        .first()
    )
    if row is None:
        raise ExchangeRateNotFound(
            f'No hay tasa {from_currency}/{to_currency} registrada en o antes del {on_date}.'
        )
    return row.rate


def _parse_number(text):
    """'36,62620000' o '1.234,56' -> Decimal (formato venezolano)."""
    cleaned = text.strip().replace('.', '').replace(',', '.')
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        raise BCVError(f'Valor de tasa no reconocido: {text!r}')


def parse_bcv_html(html):
    """Extrae la fecha valor y las tasas de la portada de bcv.org.ve."""
    rates = {}
    for block_id, currency in BCV_CURRENCY_BLOCKS.items():
        match = re.search(
            rf'id=["\']{block_id}["\'].*?<strong>\s*([\d.,]+)\s*</strong>', html, flags=re.S | re.I,
        )
        if match:
            rates[currency] = _parse_number(match.group(1))
    if 'USD' not in rates:
        raise BCVError('No se encontro la tasa del dolar en la pagina del BCV.')

    date_match = re.search(r'Fecha\s+Valor.*?content=["\'](\d{4}-\d{2}-\d{2})', html, flags=re.S | re.I)
    if not date_match:
        date_match = re.search(r'property=["\']dc:date["\'][^>]*content=["\'](\d{4}-\d{2}-\d{2})', html, flags=re.I)
    if not date_match:
        raise BCVError('No se encontro la fecha valor en la pagina del BCV.')
    return BCVRates(value_date=date.fromisoformat(date_match.group(1)), rates=rates)


def fetch_bcv_html():
    """Descarga la portada del BCV. Si el certificado del sitio da problemas,
    indica un bundle de CA propio en BCV_CA_BUNDLE (nunca se desactiva TLS)."""
    context = ssl.create_default_context(cafile=getattr(settings, 'BCV_CA_BUNDLE', None) or None)
    request = urllib.request.Request(settings.BCV_URL, headers={'User-Agent': 'Mozilla/5.0 (SGG)'})
    try:
        with urllib.request.urlopen(request, timeout=30, context=context) as response:
            return response.read().decode('utf-8', errors='replace')
    except OSError as exc:
        raise BCVError(f'No se pudo conectar con el BCV: {exc}') from exc


def tenants_using_bcv():
    """Empresas activas que llevan la contabilidad en bolivares."""
    from tenants.config import base_currency
    from tenants.models import Tenant

    return [t for t in Tenant.objects.filter(is_active=True) if base_currency(t) == 'VES']


@transaction.atomic
def store_bcv_rates(bcv_rates, tenants=None):
    """Guarda las tasas para cada empresa. Devuelve cuantas tasas se crearon o actualizaron."""
    from .models import ExchangeRate

    tenants = tenants_using_bcv() if tenants is None else tenants
    count = 0
    for tenant in tenants:
        for currency, rate in bcv_rates.rates.items():
            ExchangeRate.objects.update_or_create(
                tenant=tenant, from_currency=currency, to_currency='VES', rate_date=bcv_rates.value_date,
                defaults={'rate': rate, 'source': BCV_SOURCE},
            )
            count += 1
    return count


def update_bcv_rates(tenants=None, html=None):
    """Descarga (o usa `html`), interpreta y guarda la tasa del BCV."""
    bcv_rates = parse_bcv_html(html if html is not None else fetch_bcv_html())
    count = store_bcv_rates(bcv_rates, tenants)
    logger.info('Tasa BCV %s guardada (%s registros): %s', bcv_rates.value_date, count, bcv_rates.rates)
    return bcv_rates, count
