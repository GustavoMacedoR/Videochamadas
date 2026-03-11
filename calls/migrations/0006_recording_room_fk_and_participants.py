import json
import os
import re
import uuid

from django.db import migrations, models


ROOM_SUFFIX_FILE_PATTERN = re.compile(r'^(?P<room>.+)-\d{8}-\d{6}\.(webm|mp4|mkv)$', re.IGNORECASE)


def _normalize_roles(raw_roles):
    if isinstance(raw_roles, str):
        raw_roles = [raw_roles]
    if not isinstance(raw_roles, list):
        return []
    return [str(role).strip() for role in raw_roles if str(role).strip()]


def _normalize_participant_entry(raw_participant):
    if isinstance(raw_participant, dict):
        name = str(raw_participant.get('name') or '').strip()
        image_url = str(raw_participant.get('imageUrl') or raw_participant.get('image_url') or '').strip()
        roles = _normalize_roles(raw_participant.get('roles'))
        raw_client_id = raw_participant.get('client_id') or raw_participant.get('id')
        client_id = str(raw_client_id or '').strip()[:40]
        return {
            'name': name,
            'image_url': image_url,
            'roles': roles,
            'client_id': client_id,
        }

    name = str(raw_participant or '').strip()
    return {
        'name': name,
        'image_url': '',
        'roles': [],
        'client_id': '',
    }


def _participant_client_id(room_id, participant):
    client_id = participant.get('client_id') or ''
    if client_id:
        return client_id[:40]

    name = participant.get('name') or 'participante'
    digest = uuid.uuid5(uuid.NAMESPACE_DNS, f'{room_id}:{name}').hex[:32]
    return f'legacy-{digest}'[:40]


def _extract_room_hint_from_file(file_name):
    clean_name = os.path.basename(file_name or '').strip()
    if not clean_name:
        return ''
    match = ROOM_SUFFIX_FILE_PATTERN.match(clean_name)
    if not match:
        return ''
    return str(match.group('room') or '').strip()


def _build_room_indexes(Room):
    rooms_by_id = {}
    rooms_by_name = {}

    for room in Room.objects.all().order_by('-created_at'):
        room_id = str(room.id).strip()
        room_name = str(room.name or '').strip()
        if room_id and room_id not in rooms_by_id:
            rooms_by_id[room_id.casefold()] = room
        if room_name and room_name.casefold() not in rooms_by_name:
            rooms_by_name[room_name.casefold()] = room

    return rooms_by_id, rooms_by_name


def _resolve_room(Room, rooms_by_id, rooms_by_name, identifier):
    value = str(identifier or '').strip()
    if not value:
        return None

    room = rooms_by_id.get(value.casefold())
    if room is not None:
        return room

    room = rooms_by_name.get(value.casefold())
    if room is not None:
        return room

    try:
        parsed_uuid = uuid.UUID(value)
        room, _ = Room.objects.get_or_create(id=parsed_uuid)
        rooms_by_id[value.casefold()] = room
        room_name = str(room.name or '').strip()
        if room_name:
            rooms_by_name.setdefault(room_name.casefold(), room)
        return room
    except Exception:
        return None


def _save_participants_from_recording(RoomParticipant, room, recording):
    participants_json = getattr(recording, 'participants_json', '')
    if not participants_json:
        return

    try:
        parsed = json.loads(participants_json)
    except Exception:
        return

    if not isinstance(parsed, list):
        return

    for raw_participant in parsed:
        normalized = _normalize_participant_entry(raw_participant)
        name = normalized.get('name') or ''
        if not name:
            continue

        client_id = _participant_client_id(room.id, normalized)
        defaults = {
            'name': name[:80],
            'roles_json': json.dumps(normalized.get('roles') or []),
            'image_url': normalized.get('image_url', ''),
            'join_count': 1,
        }
        participant, created = RoomParticipant.objects.get_or_create(
            room=room,
            client_id=client_id,
            defaults=defaults,
        )
        if created:
            continue

        changed_fields = []

        if name and participant.name != name[:80]:
            participant.name = name[:80]
            changed_fields.append('name')

        existing_roles = []
        try:
            existing_roles = json.loads(participant.roles_json or '[]')
            if not isinstance(existing_roles, list):
                existing_roles = []
        except Exception:
            existing_roles = []

        merged_roles = []
        for role in existing_roles + (normalized.get('roles') or []):
            role_text = str(role).strip()
            if role_text and role_text not in merged_roles:
                merged_roles.append(role_text)

        merged_roles_json = json.dumps(merged_roles)
        if participant.roles_json != merged_roles_json:
            participant.roles_json = merged_roles_json
            changed_fields.append('roles_json')

        image_url = normalized.get('image_url', '')
        if image_url and participant.image_url != image_url:
            participant.image_url = image_url
            changed_fields.append('image_url')

        if changed_fields:
            participant.save(update_fields=changed_fields + ['last_seen_at'])


def _backfill_recording_room_and_participants(apps, schema_editor):
    Room = apps.get_model('calls', 'Room')
    Recording = apps.get_model('calls', 'Recording')
    RoomParticipant = apps.get_model('calls', 'RoomParticipant')

    rooms_by_id, rooms_by_name = _build_room_indexes(Room)
    all_rooms = list(Room.objects.all().order_by('-created_at'))
    single_room = all_rooms[0] if len(all_rooms) == 1 else None

    for recording in Recording.objects.all().iterator():
        room = None

        if recording.room_id:
            try:
                room = Room.objects.get(id=recording.room_id)
            except Room.DoesNotExist:
                room = None

        if room is None:
            room = _resolve_room(Room, rooms_by_id, rooms_by_name, recording.room_name)

        if room is None:
            room_hint = _extract_room_hint_from_file(getattr(recording.file, 'name', ''))
            room = _resolve_room(Room, rooms_by_id, rooms_by_name, room_hint)

        if room is None and single_room is not None:
            room = single_room

        if room is not None:
            changed_fields = []
            if recording.room_id != room.id:
                recording.room_id = room.id
                changed_fields.append('room')
            if not (recording.room_name or '').strip():
                recording.room_name = str(room.id)
                changed_fields.append('room_name')
            if changed_fields:
                recording.save(update_fields=changed_fields)

            _save_participants_from_recording(RoomParticipant, room, recording)


def _noop_reverse(apps, schema_editor):
    return


class Migration(migrations.Migration):

    dependencies = [
        ('calls', '0005_recording_room_name'),
    ]

    operations = [
        migrations.AddField(
            model_name='recording',
            name='room',
            field=models.ForeignKey(blank=True, null=True, on_delete=models.SET_NULL, related_name='recordings', to='calls.room'),
        ),
        migrations.CreateModel(
            name='RoomParticipant',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('client_id', models.CharField(max_length=40)),
                ('name', models.CharField(blank=True, default='', max_length=80)),
                ('roles_json', models.TextField(blank=True, default='[]')),
                ('image_url', models.URLField(blank=True, default='', max_length=500)),
                ('join_count', models.PositiveIntegerField(default=1)),
                ('first_seen_at', models.DateTimeField(auto_now_add=True)),
                ('last_seen_at', models.DateTimeField(auto_now=True)),
                ('room', models.ForeignKey(on_delete=models.CASCADE, related_name='participants', to='calls.room')),
            ],
        ),
        migrations.AddConstraint(
            model_name='roomparticipant',
            constraint=models.UniqueConstraint(fields=('room', 'client_id'), name='unique_room_participant_client'),
        ),
        migrations.RunPython(_backfill_recording_room_and_participants, _noop_reverse),
    ]
