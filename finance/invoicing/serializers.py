from rest_framework import serializers

from .models import FeeNote, FeeNoteReminder


class FeeNoteReminderSerializer(serializers.ModelSerializer):
    class Meta:
        model = FeeNoteReminder
        fields = '__all__'


class FeeNoteSerializer(serializers.ModelSerializer):
    reminders = FeeNoteReminderSerializer(many=True, read_only=True)

    class Meta:
        model = FeeNote
        fields = '__all__'
