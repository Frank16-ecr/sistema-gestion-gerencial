"""Aplica a una empresa la configuracion de un pais (moneda base y nomina).

Ejemplos:
    python manage.py configurar_pais mi-empresa VE
    python manage.py configurar_pais mi-empresa VE --riesgo medio --salario-minimo 130
    python manage.py configurar_pais mi-empresa VE --moneda USD

En Venezuela crea ademas el plan de cuentas basico (salvo --sin-plan-cuentas).
"""
from django.core.management.base import BaseCommand, CommandError

from finance.accounts.services import create_chart_of_accounts
from finance.payroll.config import (
    COUNTRY_PRESETS, PAYROLL_CONFIG_KEY, VENEZUELA_IVSS_EMPLOYER_RATES, VENEZUELA_PAYROLL_CONFIG, PayrollConfigError,
    validate_payroll_config,
)
from tenants.config import BASE_CURRENCY_KEY
from tenants.models import Tenant, TenantSetting

COUNTRY_CURRENCY = {'VE': 'VES', 'UG': 'UGX'}


class Command(BaseCommand):
    help = 'Configura la moneda base y la nomina de una empresa segun su pais.'

    def add_arguments(self, parser):
        parser.add_argument('empresa', help='slug de la empresa')
        parser.add_argument('pais', choices=sorted(COUNTRY_PRESETS), help='codigo del pais')
        parser.add_argument('--moneda', help='moneda base (por defecto, la del pais)')
        parser.add_argument('--riesgo', choices=sorted(VENEZUELA_IVSS_EMPLOYER_RATES),
                            help='VE: riesgo de la actividad para el aporte patronal del IVSS (9/10/11 %%)')
        parser.add_argument('--salario-minimo', type=float, help='salario minimo mensual vigente')
        parser.add_argument('--sin-plan-cuentas', action='store_true',
                            help='VE: no crear el plan de cuentas basico')
        parser.add_argument('--piso-pensiones', type=float,
                            help='VE: base minima por trabajador de la contribucion de pensiones')

    def handle(self, *args, **opts):
        try:
            tenant = Tenant.objects.get(slug=opts['empresa'])
        except Tenant.DoesNotExist:
            raise CommandError(f"No existe una empresa con slug '{opts['empresa']}'.")
        country = opts['pais']

        config = {'country': country}
        if opts['salario_minimo'] is not None:
            config['minimum_wage'] = opts['salario_minimo']
        if country == 'VE' and (opts['riesgo'] or opts['piso_pensiones'] is not None):
            contributions = [dict(c) for c in VENEZUELA_PAYROLL_CONFIG['contributions']]
            for c in contributions:
                if c['code'] == 'ivss' and opts['riesgo']:
                    c['employer_rate'] = VENEZUELA_IVSS_EMPLOYER_RATES[opts['riesgo']]
                if c['code'] == 'pension' and opts['piso_pensiones'] is not None:
                    c['floor_amount'] = opts['piso_pensiones']
            config['contributions'] = contributions
        elif opts['riesgo'] or opts['piso_pensiones'] is not None:
            raise CommandError('--riesgo y --piso-pensiones solo aplican a Venezuela (VE).')

        try:
            validate_payroll_config(config)
        except PayrollConfigError as exc:
            raise CommandError(str(exc))

        currency = opts['moneda'] or COUNTRY_CURRENCY[country]
        TenantSetting.objects.update_or_create(
            tenant=tenant, setting_key=PAYROLL_CONFIG_KEY, defaults={'setting_value': config})
        TenantSetting.objects.update_or_create(
            tenant=tenant, setting_key=BASE_CURRENCY_KEY, defaults={'setting_value': currency})
        self.stdout.write(self.style.SUCCESS(
            f"{tenant.name}: nomina de {country} y moneda base {currency} configuradas."))
        if country == 'VE' and not opts['sin_plan_cuentas']:
            created = create_chart_of_accounts(tenant)
            self.stdout.write(f'Plan de cuentas basico: {created} cuenta(s) creada(s).')
        self.stdout.write('Revisa con tu contador las tasas y topes vigentes antes de procesar la nomina.')
