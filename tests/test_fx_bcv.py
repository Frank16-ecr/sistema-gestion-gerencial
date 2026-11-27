"""Tasa oficial del BCV."""
import tempfile
from datetime import date
from decimal import Decimal
from io import StringIO
from unittest import mock

from django.core.management import CommandError, call_command
from django.test import TestCase

from finance.fx.models import ExchangeRate
from finance.fx.services import BCVError, ExchangeRateNotFound, get_rate, parse_bcv_html, update_bcv_rates
from finance.fx.tasks import update_bcv_rates_task
from tenants.models import Tenant, TenantSetting

from .fixtures_bcv import BCV_HTML


class BCVParserTests(TestCase):

    def test_parses_rates_and_value_date(self):
        rates = parse_bcv_html(BCV_HTML)
        self.assertEqual(rates.value_date, date(2026, 11, 26))
        self.assertEqual(rates.rates['USD'], Decimal('1440.12345678'))
        self.assertEqual(rates.rates['EUR'], Decimal('512.34510000'))
        self.assertEqual(rates.rates['CNY'], Decimal('61.20110000'))

    def test_missing_data_raises(self):
        with self.assertRaises(BCVError):
            parse_bcv_html('<html>mantenimiento</html>')
        with self.assertRaises(BCVError):
            parse_bcv_html(BCV_HTML.replace('Fecha Valor', 'X').replace('dc:date', 'x'))


class BCVStorageTests(TestCase):

    def setUp(self):
        self.ve = Tenant.objects.create(name='VE', slug='ve')
        self.us = Tenant.objects.create(name='USD', slug='us')
        TenantSetting.objects.create(tenant=self.us, setting_key='base_currency', setting_value='USD')

    def test_saves_only_for_bolivar_companies_and_is_idempotent(self):
        update_bcv_rates(html=BCV_HTML)
        update_bcv_rates(html=BCV_HTML)
        self.assertEqual(ExchangeRate.objects.filter(tenant=self.ve).count(), 3)
        self.assertFalse(ExchangeRate.objects.filter(tenant=self.us).exists())
        usd = ExchangeRate.objects.get(tenant=self.ve, from_currency='USD')
        self.assertEqual((usd.to_currency, usd.source, usd.rate_date), ('VES', 'bcv', date(2026, 11, 26)))

    def test_get_rate_uses_latest_on_or_before_date(self):
        ExchangeRate.objects.create(tenant=self.ve, from_currency='USD', to_currency='VES',
                                    rate=Decimal('400'), rate_date=date(2026, 11, 20))
        ExchangeRate.objects.create(tenant=self.ve, from_currency='USD', to_currency='VES',
                                    rate=Decimal('410'), rate_date=date(2026, 11, 24))
        self.assertEqual(get_rate(self.ve, 'USD', 'VES', date(2026, 11, 23)), Decimal('400'))
        self.assertEqual(get_rate(self.ve, 'USD', 'VES', date(2026, 11, 30)), Decimal('410'))
        self.assertEqual(get_rate(self.ve, 'VES', 'VES', date(2026, 1, 1)), Decimal('1'))
        with self.assertRaises(ExchangeRateNotFound):
            get_rate(self.ve, 'USD', 'VES', date(2026, 1, 1))

    def test_command_with_local_file(self):
        with tempfile.NamedTemporaryFile('w', suffix='.html', delete=False, encoding='utf-8') as fh:
            fh.write(BCV_HTML)
        out = StringIO()
        call_command('actualizar_tasa_bcv', '--archivo', fh.name, stdout=out)
        self.assertIn('2026-11-26', out.getvalue())
        self.assertTrue(ExchangeRate.objects.filter(tenant=self.ve, from_currency='USD').exists())

    def test_command_reports_connection_errors(self):
        with mock.patch('finance.fx.services.fetch_bcv_html', side_effect=BCVError('sin conexion')):
            with self.assertRaises(CommandError):
                call_command('actualizar_tasa_bcv', stdout=StringIO())

    def test_celery_task(self):
        with mock.patch('finance.fx.services.fetch_bcv_html', return_value=BCV_HTML):
            result = update_bcv_rates_task.apply().get()
        self.assertEqual(result['fecha_valor'], '2026-11-26')
