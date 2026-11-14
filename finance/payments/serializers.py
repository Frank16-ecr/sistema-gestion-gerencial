from rest_framework import serializers
from .models import FeeNotePayment, WHTCredit


class FeeNotePaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = FeeNotePayment
        fields = '__all__'


class WHTCreditSerializer(serializers.ModelSerializer):
    class Meta:
        model = WHTCredit
        fields = '__all__'
