from rest_framework import serializers
from .models import Room
from .models import Recording


class RoomSerializer(serializers.ModelSerializer):
    class Meta:
        model = Room
        fields = ['id', 'name', 'created_at']


class RecordingSerializer(serializers.ModelSerializer):
    class Meta:
        model = Recording
        fields = [
            'id',
            'file',
            'room_name',
            'participants_json',
            'minutes_status',
            'minutes_text',
            'minutes_error',
            'minutes_generated_at',
            'created_at',
        ]
        read_only_fields = ['minutes_status', 'minutes_text', 'minutes_error', 'minutes_generated_at']
