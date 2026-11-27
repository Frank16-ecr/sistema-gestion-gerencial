"""Configuracion por empresa (tenant) con valores por defecto globales.

Cada empresa puede sobrescribir parametros guardando un `TenantSetting` con la
clave correspondiente. Asi el sistema se adapta a distintos paises o politicas
internas sin tocar el codigo.
"""
from django.conf import settings

BASE_CURRENCY_KEY = 'base_currency'


def default_currency():
    """Moneda por defecto de los modelos (variable de entorno DEFAULT_CURRENCY)."""
    return settings.DEFAULT_CURRENCY


def get_tenant_setting(tenant, key, default=None):
    """Valor de `key` para la empresa, o `default` si no esta configurado."""
    from .models import TenantSetting

    if tenant is None:
        return default
    row = TenantSetting.objects.filter(tenant=tenant, setting_key=key).values_list('setting_value', flat=True).first()
    return default if row is None else row


def base_currency(tenant):
    """Moneda funcional de la empresa (en la que se lleva la contabilidad)."""
    return get_tenant_setting(tenant, BASE_CURRENCY_KEY, settings.DEFAULT_CURRENCY)
