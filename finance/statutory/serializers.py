from rest_framework import serializers
from .models import StatutoryObligation


class StatutoryObligationSerializer(serializers.ModelSerializer):
    class Meta:
        model = StatutoryObligation
        fields = '__all__'
