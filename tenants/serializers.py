from rest_framework import serializers
from .models import Tenant, TenantSetting


class TenantSettingSerializer(serializers.ModelSerializer):
    class Meta:
        model = TenantSetting
        fields = '__all__'


class TenantSerializer(serializers.ModelSerializer):
    settings = TenantSettingSerializer(many=True, read_only=True)

    class Meta:
        model = Tenant
        fields = '__all__'
