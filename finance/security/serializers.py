from rest_framework import serializers

from .models import UserTenantRole


class UserTenantRoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserTenantRole
        fields = '__all__'
        read_only_fields = ('assigned_by', 'created_at')
