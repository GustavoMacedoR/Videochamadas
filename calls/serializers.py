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
        fields = ['id', 'file', 'created_at']
