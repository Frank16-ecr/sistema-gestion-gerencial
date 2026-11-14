from rest_framework import serializers
from .models import BankAccount, BankReconciliation, PettyCashTransaction, Cheque


class BankAccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = BankAccount
        fields = '__all__'


class BankReconciliationSerializer(serializers.ModelSerializer):
    class Meta:
        model = BankReconciliation
        fields = '__all__'


class PettyCashTransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = PettyCashTransaction
        fields = '__all__'


class ChequeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Cheque
        fields = '__all__'
