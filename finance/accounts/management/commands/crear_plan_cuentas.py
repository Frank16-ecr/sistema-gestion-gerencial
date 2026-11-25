"""Crea el plan de cuentas basico venezolano en una empresa (no duplica cuentas existentes).

    python manage.py crear_plan_cuentas mi-empresa
"""
from django.core.management.base import BaseCommand, CommandError

from finance.accounts.services import create_chart_of_accounts
from tenants.models import Tenant


class Command(BaseCommand):
    help = 'Crea el plan de cuentas basico (Venezuela) para una empresa.'

    def add_arguments(self, parser):
        parser.add_argument('empresa', help='slug de la empresa')

    def handle(self, *args, **opts):
        try:
            tenant = Tenant.objects.get(slug=opts['empresa'])
        except Tenant.DoesNotExist:
            raise CommandError(f"No existe una empresa con slug '{opts['empresa']}'.")
        created = create_chart_of_accounts(tenant)
        self.stdout.write(self.style.SUCCESS(f'{tenant.name}: {created} cuenta(s) creada(s).'))
