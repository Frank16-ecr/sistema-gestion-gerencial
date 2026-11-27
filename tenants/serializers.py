from rest_framework import serializers

from .models import Tenant, TenantSetting


class TenantSettingSerializer(serializers.ModelSerializer):
    class Meta:
        model = TenantSetting
        fields = '__all__'

    def validate(self, attrs):
        from finance.payroll.config import PAYROLL_CONFIG_KEY, PayrollConfigError, validate_payroll_config

        from .config import BASE_CURRENCY_KEY

        key = attrs.get('setting_key', getattr(self.instance, 'setting_key', None))
        value = attrs.get('setting_value', getattr(self.instance, 'setting_value', None))
        if key == PAYROLL_CONFIG_KEY:
            try:
                validate_payroll_config(value)
            except (PayrollConfigError, TypeError, ArithmeticError, ValueError) as exc:
                raise serializers.ValidationError({'setting_value': str(exc)})
        elif key == BASE_CURRENCY_KEY:
            if not isinstance(value, str) or not 3 <= len(value) <= 10:
                raise serializers.ValidationError({'setting_value': 'Indica un codigo de moneda, p. ej. "USD".'})
        return attrs


class TenantSerializer(serializers.ModelSerializer):
    settings = TenantSettingSerializer(many=True, read_only=True)

    class Meta:
        model = Tenant
        fields = '__all__'
