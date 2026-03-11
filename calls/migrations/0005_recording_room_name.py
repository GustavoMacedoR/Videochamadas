import os
import re

from django.db import migrations, models


ROOM_SUFFIX_FILE_PATTERN = re.compile(r'^(?P<room>.+)-\d{8}-\d{6}\.(webm|mp4|mkv)$', re.IGNORECASE)


def _backfill_recording_room_name(apps, schema_editor):
    Recording = apps.get_model('calls', 'Recording')
    Room = apps.get_model('calls', 'Room')

    rooms = list(Room.objects.all())
    if not rooms:
        return

    single_room_id = str(rooms[0].id) if len(rooms) == 1 else ''
    room_candidates = []
    for room in rooms:
        room_id = str(room.id).strip()
        room_name = (room.name or '').strip()
        room_candidates.append((room_id.casefold(), room_id))
        if room_name:
            room_candidates.append((room_name.casefold(), room_name))

    for recording in Recording.objects.filter(room_name='').iterator():
        inferred = ''
        file_name = os.path.basename(getattr(recording.file, 'name', '') or '').strip()

        match = ROOM_SUFFIX_FILE_PATTERN.match(file_name)
        if match:
            inferred = str(match.group('room') or '').strip()

        if not inferred:
            lowered = file_name.casefold()
            for candidate_lower, candidate_value in room_candidates:
                if candidate_lower and candidate_lower in lowered:
                    inferred = candidate_value
                    break

        if not inferred and single_room_id:
            inferred = single_room_id

        if inferred:
            recording.room_name = inferred
            recording.save(update_fields=['room_name'])


def _noop_reverse(apps, schema_editor):
    return


class Migration(migrations.Migration):

    dependencies = [
        ('calls', '0004_roomrecordingstate'),
    ]

    operations = [
        migrations.AddField(
            model_name='recording',
            name='room_name',
            field=models.CharField(blank=True, default='', max_length=200),
        ),
        migrations.RunPython(_backfill_recording_room_name, _noop_reverse),
    ]
