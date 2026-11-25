"""Parametros de nomina configurables por empresa.

Por defecto se usan las reglas de Uganda con las que nacio el sistema (PAYE +
NSSF). Para otro pais o politica, guarda un TenantSetting con la clave
``payroll_config`` y un JSON como este (solo hace falta incluir lo que cambia):

    {
        "income_tax": {
            "code": "paye",
            "bands": [[235000, 0], [335000, 10], [410000, 20], [10000000, 30], [null, 40]]
        },
        "social_security": {
            "code": "nssf",
            "employee_rate": 5,
            "employer_rate": 10,
            "monthly_cap": null
        },
        "due_day": 15
    }

`bands` es una lista de tramos [limite_superior_mensual, tasa_en_porcentaje];
el ultimo tramo lleva `null` como limite (sin tope). `monthly_cap` limita la
base de calculo de la seguridad social (null = sin tope). `code` es el tipo de
obligacion que se crea en el modulo statutory.
"""
import copy
from decimal import Decimal

from tenants.config import get_tenant_setting

PAYROLL_CONFIG_KEY = 'payroll_config'

UGANDA_PAYROLL_CONFIG = {
    'income_tax': {
        'code': 'paye',
        'bands': [[235000, 0], [335000, 10], [410000, 20], [10000000, 30], [None, 40]],
    },
    'social_security': {
        'code': 'nssf',
        'employee_rate': 5,
        'employer_rate': 10,
        'monthly_cap': None,
    },
    'due_day': 15,
}

DEFAULT_PAYROLL_CONFIG = UGANDA_PAYROLL_CONFIG


class PayrollConfigError(ValueError):
    """La configuracion de nomina guardada para la empresa no es valida."""


def _merge(base, override):
    result = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge(result[key], value)
        else:
            result[key] = value
    return result


def validate_payroll_config(config):
    """Comprueba la estructura y devuelve la configuracion completa."""
    if not isinstance(config, dict):
        raise PayrollConfigError('payroll_config debe ser un objeto JSON.')
    merged = _merge(DEFAULT_PAYROLL_CONFIG, config)

    bands = merged['income_tax'].get('bands')
    if not isinstance(bands, list) or not bands:
        raise PayrollConfigError('income_tax.bands debe ser una lista de tramos no vacia.')
    previous = Decimal('0')
    for i, band in enumerate(bands):
        if not isinstance(band, (list, tuple)) or len(band) != 2:
            raise PayrollConfigError(f'El tramo {i + 1} debe tener la forma [limite, tasa].')
        limit, rate = band
        if limit is None:
            if i != len(bands) - 1:
                raise PayrollConfigError('Solo el ultimo tramo puede no tener limite (null).')
        elif Decimal(str(limit)) <= previous:
            raise PayrollConfigError('Los limites de los tramos deben ser crecientes.')
        else:
            previous = Decimal(str(limit))
        if not 0 <= Decimal(str(rate)) <= 100:
            raise PayrollConfigError('Las tasas deben estar entre 0 y 100.')

    social = merged['social_security']
    for key in ('employee_rate', 'employer_rate'):
        if not 0 <= Decimal(str(social.get(key, 0))) <= 100:
            raise PayrollConfigError(f'social_security.{key} debe estar entre 0 y 100.')

    if not 1 <= int(merged.get('due_day', 15)) <= 31:
        raise PayrollConfigError('due_day debe estar entre 1 y 31.')
    return merged


def get_payroll_config(tenant):
    """Configuracion efectiva de nomina para la empresa."""
    return validate_payroll_config(get_tenant_setting(tenant, PAYROLL_CONFIG_KEY, {}))
