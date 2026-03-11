import uuid
from django.db import models


class Room(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name or str(self.id)


class Recording(models.Model):
    MINUTES_PENDING = 'pending'
    MINUTES_PROCESSING = 'processing'
    MINUTES_DONE = 'done'
    MINUTES_FAILED = 'failed'
    MINUTES_STATUS_CHOICES = [
        (MINUTES_PENDING, 'Pending'),
        (MINUTES_PROCESSING, 'Processing'),
        (MINUTES_DONE, 'Done'),
        (MINUTES_FAILED, 'Failed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    room = models.ForeignKey('Room', on_delete=models.SET_NULL, null=True, blank=True, related_name='recordings')
    file = models.FileField(upload_to='recordings/')
    room_name = models.CharField(max_length=200, blank=True, default='')
    participants_json = models.TextField(blank=True, default='')
    minutes_status = models.CharField(max_length=20, choices=MINUTES_STATUS_CHOICES, default=MINUTES_PENDING)
    minutes_text = models.TextField(blank=True, default='')
    minutes_error = models.TextField(blank=True, default='')
    minutes_generated_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return str(self.file.name)


class RoomParticipant(models.Model):
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='participants')
    client_id = models.CharField(max_length=40)
    name = models.CharField(max_length=80, blank=True, default='')
    roles_json = models.TextField(blank=True, default='[]')
    image_url = models.URLField(max_length=500, blank=True, default='')
    join_count = models.PositiveIntegerField(default=1)
    first_seen_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['room', 'client_id'], name='unique_room_participant_client'),
        ]

    def __str__(self):
        return f"{self.room_id}:{self.client_id}"


class RoomRecordingState(models.Model):
    room_name = models.CharField(max_length=200, unique=True)
    is_recording = models.BooleanField(default=False)
    started_by = models.CharField(max_length=200, blank=True, default='')
    process_pid = models.IntegerField(null=True, blank=True)
    process_token = models.CharField(max_length=64, blank=True, default='')
    started_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.room_name} ({'recording' if self.is_recording else 'idle'})"
