"""Parametros de nomina configurables por empresa.

Se guardan en un TenantSetting con la clave ``payroll_config``. Lo mas simple es
partir de un preset de pais y cambiar solo lo necesario:

    {"country": "VE", "minimum_wage": 130}

Estructura completa (todas las claves son opcionales):

    {
        "country": "VE",              # preset base: "VE" (Venezuela) o "UG" (Uganda); por defecto PAYROLL_COUNTRY
        "minimum_wage": 130,          # salario minimo mensual, para topes en salarios minimos
        "due_day": 15,                # dia del mes siguiente en que vencen las obligaciones
        "income_tax": {
            "code": "islr",           # tipo de obligacion que se genera
            "method": "employee_rate",# "employee_rate" (% por trabajador, AR-I) o "bands"
            "bands": [[1000, 0], [null, 10]]   # solo con method="bands": [limite, tasa %]
        },
        "contributions": [            # aportes sobre la nomina (reemplaza la lista completa)
            {
                "code": "ivss", "name": "Seguro Social",
                "employee_rate": 4, "employer_rate": 9,
                "base": "salary",         # "salary" (salario) o "total" (salario + asignaciones)
                "cap_minimum_wages": 5,   # tope de la base en salarios minimos (opcional)
                "cap_amount": null,       # tope de la base en importe fijo (opcional)
                "floor_amount": null,     # base minima por trabajador (opcional)
                "due_day": 5              # vencimiento propio (opcional)
            }
        ]
    }

Con "bands", cada tramo es [limite_superior_mensual, tasa_en_porcentaje] y el
ultimo lleva `null` como limite. Con "employee_rate" se aplica el porcentaje de
retencion de cada trabajador (campo `income_tax_rate` de su ficha).

Por compatibilidad, si no hay "contributions" se usa la clave antigua
"social_security" ({code, employee_rate, employer_rate, monthly_cap}).

IMPORTANTE: las tasas y topes de los presets son orientativos. Las cifras
legales cambian por Gaceta Oficial; confirmalas con tu contador y ajustalas en
la configuracion de cada empresa.
"""
import copy
from decimal import Decimal, InvalidOperation

from django.conf import settings

from tenants.config import get_tenant_setting

PAYROLL_CONFIG_KEY = 'payroll_config'

INCOME_TAX_METHODS = ('bands', 'employee_rate')
CONTRIBUTION_BASES = ('salary', 'total')

UGANDA_PAYROLL_CONFIG = {
    'country': 'UG',
    'minimum_wage': None,
    'due_day': 15,
    'income_tax': {
        'code': 'paye',
        'method': 'bands',
        'bands': [[235000, 0], [335000, 10], [410000, 20], [10000000, 30], [None, 40]],
    },
    'social_security': {
        'code': 'nssf',
        'employee_rate': 5,
        'employer_rate': 10,
        'monthly_cap': None,
    },
}

# Venezuela (referencias de 2026; verificar contra la Gaceta Oficial vigente).
# - ISLR: retencion por trabajador segun el porcentaje del AR-I (Decreto 1.808).
# - IVSS: 4% trabajador; patrono 9%, 10% u 11% segun el riesgo; tope 5 salarios minimos.
# - RPE (paro forzoso): 0,5% trabajador, 2% patrono; tope 10 salarios minimos.
# - FAOV (BANAVIH): 1% trabajador, 2% patrono, sobre el salario integral, sin tope.
# - INCES: 2% patrono sobre la nomina (el 0,5% del trabajador es sobre utilidades).
# - Proteccion de Pensiones: 9% patrono sobre salarios y bonificaciones; la base por
#   trabajador no puede ser menor al ingreso minimo integral indexado (floor_amount).
VENEZUELA_PAYROLL_CONFIG = {
    'country': 'VE',
    'minimum_wage': 130,
    'due_day': 15,
    'income_tax': {
        'code': 'islr',
        'method': 'employee_rate',
        'bands': [],
    },
    'contributions': [
        {'code': 'ivss', 'name': 'Seguro Social (IVSS)', 'employee_rate': 4, 'employer_rate': 9,
         'base': 'salary', 'cap_minimum_wages': 5},
        {'code': 'rpe', 'name': 'Regimen Prestacional de Empleo', 'employee_rate': 0.5, 'employer_rate': 2,
         'base': 'salary', 'cap_minimum_wages': 10},
        {'code': 'faov', 'name': 'Vivienda y Habitat (FAOV)', 'employee_rate': 1, 'employer_rate': 2,
         'base': 'total'},
        {'code': 'inces', 'name': 'INCES', 'employee_rate': 0, 'employer_rate': 2, 'base': 'total'},
        {'code': 'pension', 'name': 'Proteccion de Pensiones', 'employee_rate': 0, 'employer_rate': 9,
         'base': 'total', 'floor_amount': None},
    ],
}

# Aporte patronal del IVSS segun el riesgo de la actividad.
VENEZUELA_IVSS_EMPLOYER_RATES = {'bajo': 9, 'medio': 10, 'alto': 11}

COUNTRY_PRESETS = {'UG': UGANDA_PAYROLL_CONFIG, 'VE': VENEZUELA_PAYROLL_CONFIG}
# Tramos por defecto de las funciones de calculo sueltas (calculate_paye / calculate_nssf).
DEFAULT_PAYROLL_CONFIG = UGANDA_PAYROLL_CONFIG


class PayrollConfigError(ValueError):
    """La configuracion de nomina guardada para la empresa no es valida."""


def _merge(base, override):
    result = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def _decimal(value, label):
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise PayrollConfigError(f'{label} debe ser un numero.')


def _check_rate(value, label):
    if not 0 <= _decimal(value, label) <= 100:
        raise PayrollConfigError(f'{label} debe estar entre 0 y 100.')


def _check_due_day(value, label):
    try:
        ok = 1 <= int(value) <= 31
    except (TypeError, ValueError):
        ok = False
    if not ok:
        raise PayrollConfigError(f'{label} debe estar entre 1 y 31.')


def _validate_bands(bands):
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
        elif _decimal(limit, 'El limite del tramo') <= previous:
            raise PayrollConfigError('Los limites de los tramos deben ser crecientes.')
        else:
            previous = Decimal(str(limit))
        _check_rate(rate, f'La tasa del tramo {i + 1}')


def _legacy_contributions(social):
    return [{
        'code': social.get('code', 'social_security'),
        'name': 'Seguridad social',
        'employee_rate': social.get('employee_rate', 0),
        'employer_rate': social.get('employer_rate', 0),
        'base': 'salary',
        'cap_amount': social.get('monthly_cap'),
    }]


def _validate_contributions(contributions, minimum_wage):
    if not isinstance(contributions, list):
        raise PayrollConfigError('contributions debe ser una lista.')
    codes = set()
    for i, c in enumerate(contributions):
        label = f'contributions[{i}]'
        if not isinstance(c, dict) or not c.get('code'):
            raise PayrollConfigError(f'{label} debe ser un objeto con "code".')
        if c['code'] in codes:
            raise PayrollConfigError(f'El codigo de aporte "{c["code"]}" esta repetido.')
        codes.add(c['code'])
        c.setdefault('name', c['code'])
        c.setdefault('base', 'salary')
        c.setdefault('employee_rate', 0)
        c.setdefault('employer_rate', 0)
        _check_rate(c['employee_rate'], f'{label}.employee_rate')
        _check_rate(c['employer_rate'], f'{label}.employer_rate')
        if c['base'] not in CONTRIBUTION_BASES:
            raise PayrollConfigError(f'{label}.base debe ser "salary" o "total".')
        for key in ('cap_amount', 'floor_amount', 'cap_minimum_wages'):
            if c.get(key) is not None and _decimal(c[key], f'{label}.{key}') < 0:
                raise PayrollConfigError(f'{label}.{key} no puede ser negativo.')
        if c.get('cap_minimum_wages') is not None and minimum_wage is None:
            raise PayrollConfigError(f'{label} usa cap_minimum_wages pero no hay minimum_wage configurado.')
        if c.get('due_day') is not None:
            _check_due_day(c['due_day'], f'{label}.due_day')
    return contributions


def validate_payroll_config(config):
    """Comprueba la estructura y devuelve la configuracion completa y normalizada."""
    if not isinstance(config, dict):
        raise PayrollConfigError('payroll_config debe ser un objeto JSON.')
    country = config.get('country', settings.PAYROLL_COUNTRY)
    if country not in COUNTRY_PRESETS:
        raise PayrollConfigError(f'Pais no soportado: {country}. Opciones: {", ".join(COUNTRY_PRESETS)}.')
    merged = _merge(COUNTRY_PRESETS[country], config)

    income_tax = merged['income_tax']
    user_tax = config.get('income_tax') or {}
    if isinstance(user_tax, dict) and 'bands' in user_tax and 'method' not in user_tax:
        # Quien define tramos quiere calcular por tramos, aunque el preset use otro metodo.
        income_tax['method'] = 'bands'
    income_tax.setdefault('method', 'bands')
    if income_tax['method'] not in INCOME_TAX_METHODS:
        raise PayrollConfigError('income_tax.method debe ser "bands" o "employee_rate".')
    if income_tax['method'] == 'bands':
        _validate_bands(income_tax.get('bands'))

    minimum_wage = merged.get('minimum_wage')
    if minimum_wage is not None and _decimal(minimum_wage, 'minimum_wage') <= 0:
        raise PayrollConfigError('minimum_wage debe ser mayor que cero.')

    # Prioridad: lista propia de la empresa > clave antigua social_security > preset del pais.
    use_legacy = 'contributions' not in config and (
        'social_security' in config or 'contributions' not in merged
    )
    if use_legacy:
        social = merged.get('social_security') or {}
        for key in ('employee_rate', 'employer_rate'):
            _check_rate(social.get(key, 0), f'social_security.{key}')
        contributions = _legacy_contributions(social)
    else:
        contributions = merged['contributions']
    merged['contributions'] = _validate_contributions(contributions, minimum_wage)

    _check_due_day(merged.get('due_day', 15), 'due_day')
    return merged


def get_payroll_config(tenant):
    """Configuracion efectiva de nomina para la empresa."""
    return validate_payroll_config(get_tenant_setting(tenant, PAYROLL_CONFIG_KEY, {}))


def contribution_base(contribution, salary, total, minimum_wage):
    """Base de calculo de un aporte, aplicando piso y tope."""
    base = Decimal(str(total if contribution.get('base') == 'total' else salary))
    floor = contribution.get('floor_amount')
    if floor is not None:
        base = max(base, Decimal(str(floor)))
    caps = []
    if contribution.get('cap_amount') is not None:
        caps.append(Decimal(str(contribution['cap_amount'])))
    if contribution.get('cap_minimum_wages') is not None:
        caps.append(Decimal(str(contribution['cap_minimum_wages'])) * Decimal(str(minimum_wage)))
    if caps:
        base = min(base, *caps)
    return base
