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
        # Estado y totales solo cambian con las acciones run_monthly y approve.
        read_only_fields = (
            'status', 'period_start', 'period_end', 'mondays', 'total_gross', 'total_paye', 'total_nssf_employee',
            'total_nssf_employer', 'total_net', 'contributions_summary', 'approved_by', 'approved_at',
            'created_by', 'journal_entry', 'created_at',
        )
