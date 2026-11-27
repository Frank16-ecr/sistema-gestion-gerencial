"""Descarga la tasa oficial del BCV y la guarda para las empresas que contabilizan en VES.

    python manage.py actualizar_tasa_bcv
    python manage.py actualizar_tasa_bcv --archivo portada_bcv.html   # sin conexion
"""
from django.core.management.base import BaseCommand, CommandError

from finance.fx.services import BCVError, update_bcv_rates


class Command(BaseCommand):
    help = 'Actualiza la tasa de cambio oficial del BCV.'

    def add_arguments(self, parser):
        parser.add_argument('--archivo', help='HTML de la portada del BCV guardado localmente')

    def handle(self, *args, **opts):
        html = None
        if opts['archivo']:
            with open(opts['archivo'], encoding='utf-8', errors='replace') as fh:
                html = fh.read()
        try:
            bcv_rates, count = update_bcv_rates(html=html)
        except BCVError as exc:
            raise CommandError(str(exc))
        rates = ', '.join(f'{c} {r}' for c, r in bcv_rates.rates.items())
        self.stdout.write(self.style.SUCCESS(
            f'Tasa BCV con fecha valor {bcv_rates.value_date}: {rates} ({count} registros guardados).'))
