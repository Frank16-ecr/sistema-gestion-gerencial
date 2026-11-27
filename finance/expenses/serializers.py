from rest_framework import serializers

from .models import Expense, ReimbursementBatch, ReimbursementRequest


class ExpenseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Expense
        fields = '__all__'


class ReimbursementBatchSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReimbursementBatch
        fields = '__all__'


class ReimbursementRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReimbursementRequest
        fields = '__all__'
