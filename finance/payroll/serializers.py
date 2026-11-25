from rest_framework import serializers

from .models import EmployeeAllowance, EmployeePayrollProfile, PayrollLine, PayrollRun


class EmployeeAllowanceSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmployeeAllowance
        fields = '__all__'


class EmployeePayrollProfileSerializer(serializers.ModelSerializer):
    allowances = EmployeeAllowanceSerializer(many=True, read_only=True)

    class Meta:
        model = EmployeePayrollProfile
        fields = '__all__'


class PayrollLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = PayrollLine
        fields = '__all__'


class PayrollRunSerializer(serializers.ModelSerializer):
    lines = PayrollLineSerializer(many=True, read_only=True)

    class Meta:
        model = PayrollRun
        fields = '__all__'
