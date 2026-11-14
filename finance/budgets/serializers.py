from rest_framework import serializers

from .models import Budget, BudgetLine


class BudgetLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = BudgetLine
        fields = '__all__'


class BudgetSerializer(serializers.ModelSerializer):
    lines = BudgetLineSerializer(many=True, read_only=True)

    class Meta:
        model = Budget
        fields = '__all__'
        read_only_fields = ('created_by', 'approved_by', 'approved_at', 'created_at')

    def validate(self, attrs):
        start = attrs.get('period_start', getattr(self.instance, 'period_start', None))
        end = attrs.get('period_end', getattr(self.instance, 'period_end', None))
        if start and end and end < start:
            raise serializers.ValidationError("period_end no puede ser anterior a period_start.")
        return attrs
