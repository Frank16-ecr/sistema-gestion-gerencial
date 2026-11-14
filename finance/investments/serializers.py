from rest_framework import serializers

from .models import Investment, InvestmentMovement


class InvestmentMovementSerializer(serializers.ModelSerializer):
    class Meta:
        model = InvestmentMovement
        fields = '__all__'
        read_only_fields = ('created_at',)

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("El monto debe ser mayor que cero.")
        return value


class InvestmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Investment
        fields = '__all__'
        read_only_fields = ('created_by', 'created_at')

    def validate(self, attrs):
        start = attrs.get('start_date', getattr(self.instance, 'start_date', None))
        maturity = attrs.get('maturity_date', getattr(self.instance, 'maturity_date', None))
        if start and maturity and maturity < start:
            raise serializers.ValidationError("maturity_date no puede ser anterior a start_date.")
        return attrs
