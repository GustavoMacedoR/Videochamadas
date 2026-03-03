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
    file = models.FileField(upload_to='recordings/')
    participants_json = models.TextField(blank=True, default='')
    minutes_status = models.CharField(max_length=20, choices=MINUTES_STATUS_CHOICES, default=MINUTES_PENDING)
    minutes_text = models.TextField(blank=True, default='')
    minutes_error = models.TextField(blank=True, default='')
    minutes_generated_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return str(self.file.name)
