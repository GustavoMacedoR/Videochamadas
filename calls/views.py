from rest_framework import viewsets, status
from rest_framework.views import APIView
from rest_framework.response import Response
from .models import Room, Recording, RoomParticipant
from .serializers import RoomSerializer
from .serializers import RecordingSerializer
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import AllowAny
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from django.core.files.base import File
from django.db.models import Q
from datetime import timezone as datetime_timezone
from pathlib import Path
from urllib.parse import urlparse
from uuid import UUID, uuid4
import os
import json
import re
import math

from .transcription import enqueue_minutes_generation
from .server_recording import start_server_recording, stop_server_recording, get_room_recording_status, notify_recording_ready


MINUTES_RANGE_PATTERN = re.compile(r'\[(\d{2}:\d{2}:\d{2})-(\d{2}:\d{2}:\d{2})\]')
ROOM_SUFFIX_FILE_PATTERN = re.compile(r'^(?P<room>.+)-\d{8}-\d{6}\.(webm|mp4|mkv)$', re.IGNORECASE)
ROOM_SUFFIX_UPLOAD_PATTERN = re.compile(r'^(?P<room>.+)-[0-9a-f]{32}$', re.IGNORECASE)


def _filter_rooms_queryset(request):
    qs = Room.objects.all().order_by('-created_at')
    name = request.query_params.get('name', '').strip()
    id_q = request.query_params.get('id', '').strip()
    date_q = request.query_params.get('date', '').strip()
    if name:
        qs = qs.filter(name__icontains=name)
    if id_q:
        qs = qs.filter(id__icontains=id_q)
    if date_q:
        try:
            qs = qs.filter(created_at__date=date_q)
        except (ValueError, TypeError):
            pass
    return qs


def _filter_recordings_queryset(request):
    qs = Recording.objects.all().order_by('-created_at')
    if request is None:
        return qs

    room_value = str(request.query_params.get('room_id') or request.query_params.get('room_name') or '').strip()
    if not room_value:
        return qs

    room_obj = _resolve_room_from_identifier(room_value, create_if_missing=False)
    if room_obj is None:
        return qs.filter(room_name__iexact=room_value)

    room_id_text = str(room_obj.id)
    room_name_text = (room_obj.name or '').strip()

    room_name_filters = Q(room_name__iexact=room_id_text)
    if room_name_text:
        room_name_filters |= Q(room_name__iexact=room_name_text)

    return qs.filter(Q(room=room_obj) | room_name_filters)


def _normalize_relative_client_url(raw_url):
    value = str(raw_url or '').strip()
    if not value:
        return ''
    if value.startswith('/'):
        return value

    try:
        parsed = urlparse(value)
    except Exception:
        return value

    if not parsed.scheme and not parsed.netloc:
        return value

    path = parsed.path or ''
    if parsed.query:
        path = f'{path}?{parsed.query}'
    if parsed.fragment:
        path = f'{path}#{parsed.fragment}'
    return path or value


def _format_datetime_iso8601(value):
    if value is None:
        return None
    try:
        if value.tzinfo is not None:
            value = value.astimezone(datetime_timezone.utc)
        formatted = value.isoformat(timespec='milliseconds')
        if formatted.endswith('+00:00'):
            return formatted.replace('+00:00', 'Z')
        return formatted
    except Exception:
        return str(value)


def _resolve_room_from_identifier(identifier, create_if_missing=False):
    value = str(identifier or '').strip()
    if not value:
        return None

    try:
        parsed_uuid = UUID(value)
        room = Room.objects.filter(id=parsed_uuid).first()
        if room is not None:
            return room
        if create_if_missing:
            return Room.objects.create(id=parsed_uuid)
        return None
    except (ValueError, TypeError, AttributeError):
        pass

    room = Room.objects.filter(name__iexact=value).order_by('-created_at').first()
    if room is not None:
        return room

    if create_if_missing:
        return Room.objects.create(name=value)
    return None


def _normalize_roles(raw_roles):
    if isinstance(raw_roles, str):
        raw_roles = [raw_roles]
    if not isinstance(raw_roles, list):
        return []
    return [str(role).strip() for role in raw_roles if str(role).strip()]


def _normalize_participant_payload(raw_participant):
    if isinstance(raw_participant, dict):
        client_id = raw_participant.get('clientId')
        if client_id is None:
            client_id = raw_participant.get('client_id')
        client_id = str(client_id or '').strip()[:40] or None

        name = str(raw_participant.get('name', '')).strip()
        if not name and not client_id:
            return None
        if not name:
            name = f"Participante {client_id[:6]}" if client_id else 'Participante'

        image_url = raw_participant.get('imageUrl')
        if image_url is None:
            image_url = raw_participant.get('image_url')
        image_url = str(image_url).strip() if image_url else None
        return {
            'clientId': client_id,
            'name': name,
            'roles': _normalize_roles(raw_participant.get('roles')),
            'imageUrl': image_url,
        }

    name = str(raw_participant or '').strip()
    if not name:
        return None
    return {
        'clientId': None,
        'name': name,
        'roles': [],
        'imageUrl': None,
    }


def _sync_recordings_from_disk():
    recordings_dir = Path(settings.MEDIA_ROOT) / 'recordings'
    recordings_dir.mkdir(parents=True, exist_ok=True)
    known_names = set(Recording.objects.values_list('file', flat=True))
    for fpath in sorted(recordings_dir.iterdir()):
        if fpath.suffix.lower() not in {'.webm', '.mp4', '.mkv'}:
            continue
        relative = f'recordings/{fpath.name}'
        if relative not in known_names:
            room_hint = _extract_room_name_hint('', fpath.name, '')
            room_obj = _resolve_room_from_identifier(room_hint, create_if_missing=False)
            try:
                Recording.objects.create(
                    file=relative,
                    room=room_obj,
                    room_name=room_hint if room_hint else '',
                )
            except Exception:
                pass


def _extract_room_name_hint(room_name, filename, upload_id):
    clean_room_name = str(room_name or '').strip()
    if clean_room_name:
        return clean_room_name

    file_name = os.path.basename(str(filename or '').strip())
    file_match = ROOM_SUFFIX_FILE_PATTERN.match(file_name)
    if file_match:
        return str(file_match.group('room') or '').strip()

    upload_value = str(upload_id or '').strip()
    upload_match = ROOM_SUFFIX_UPLOAD_PATTERN.match(upload_value)
    if upload_match:
        return str(upload_match.group('room') or '').strip()

    return ''


def _parse_recording_participants(recording):
    if not recording.participants_json:
        return []
    try:
        parsed = json.loads(recording.participants_json)
    except Exception:
        return []

    if isinstance(parsed, list):
        return parsed
    return [parsed]


def _normalize_participant(raw_participant):
    return _normalize_participant_payload(raw_participant)


def _merge_participants(recordings):
    participants_by_identity = {}

    for recording in recordings:
        for participant in _parse_recording_participants(recording):
            normalized = _normalize_participant(participant)
            if not normalized:
                continue

            participant_key = normalized.get('clientId') or normalized['name'].casefold()
            current = participants_by_identity.get(participant_key)
            if current is None:
                participants_by_identity[participant_key] = {
                    'clientId': normalized.get('clientId'),
                    'name': normalized['name'],
                    'roles': list(normalized.get('roles') or []),
                    'imageUrl': normalized.get('imageUrl'),
                }
                continue

            current_roles = set(current['roles'])
            for role in normalized['roles']:
                if role not in current_roles:
                    current['roles'].append(role)
                    current_roles.add(role)

            if not current.get('imageUrl') and normalized.get('imageUrl'):
                current['imageUrl'] = normalized['imageUrl']

    return list(participants_by_identity.values())


def _participant_payload_from_room(room):
    participants = []
    qs = RoomParticipant.objects.filter(room=room).order_by('first_seen_at')
    for participant in qs:
        roles = []
        try:
            raw_roles = json.loads(participant.roles_json or '[]')
            if isinstance(raw_roles, list):
                roles = [str(role).strip() for role in raw_roles if str(role).strip()]
        except Exception:
            roles = []

        name = (participant.name or '').strip()
        if not name:
            name = f"Participante {participant.client_id[:6]}"

        image_url = (participant.image_url or '').strip()
        participants.append({
            'clientId': participant.client_id,
            'name': name,
            'roles': roles,
            'imageUrl': image_url or None,
        })
    return participants


def _participants_json_from_room(room):
    payload = _participant_payload_from_room(room)
    if not payload:
        return ''
    return json.dumps(payload, ensure_ascii=False)


def _participants_json_has_entries(participants_json):
    text = str(participants_json or '').strip()
    if not text:
        return False
    try:
        data = json.loads(text)
    except Exception:
        return False
    if not isinstance(data, list):
        return False
    for item in data:
        if _normalize_participant_payload(item):
            return True
    return False


def _merge_participant_payloads(primary_participants, secondary_participants):
    participants_by_identity = {}

    for source in [primary_participants or [], secondary_participants or []]:
        for raw_participant in source:
            participant = _normalize_participant_payload(raw_participant)
            if not participant:
                continue

            client_id = participant.get('clientId')
            key = f"id:{client_id.casefold()}" if client_id else f"name:{participant['name'].casefold()}"
            current = participants_by_identity.get(key)
            if current is None:
                participants_by_identity[key] = {
                    'clientId': client_id,
                    'name': participant['name'],
                    'roles': list(participant.get('roles') or []),
                    'imageUrl': participant.get('imageUrl'),
                }
                continue

            known_roles = set(current['roles'])
            for role in participant.get('roles') or []:
                if role not in known_roles:
                    current['roles'].append(role)
                    known_roles.add(role)

            if not current.get('imageUrl') and participant.get('imageUrl'):
                current['imageUrl'] = participant['imageUrl']

    payload = []
    for participant in participants_by_identity.values():
        payload.append({
            'name': participant['name'],
            'roles': list(participant.get('roles') or []),
            'imageUrl': participant.get('imageUrl'),
        })
    return payload


def _recording_matches_room(recording, room):
    if recording.room_id and str(recording.room_id) == str(room.id):
        return True

    recording_room_name = (recording.room_name or '').strip().casefold()
    room_id = str(room.id).casefold()
    room_name = (room.name or '').strip().casefold()

    if recording_room_name:
        if recording_room_name == room_id:
            return True
        if room_name and recording_room_name == room_name:
            return True

    if not recording.file:
        return False

    file_name = (recording.file.name or '').strip().casefold()
    if not file_name:
        return False

    if room_id and room_id in file_name:
        return True
    if room_name and room_name in file_name:
        return True
    return False


def _hhmmss_to_seconds(value):
    try:
        hours, minutes, seconds = value.split(':')
        return int(hours) * 3600 + int(minutes) * 60 + int(seconds)
    except Exception:
        return 0


def _estimate_duration_label(recording):
    max_seconds = 0
    minutes_text = recording.minutes_text or ''

    for _start, end in MINUTES_RANGE_PATTERN.findall(minutes_text):
        max_seconds = max(max_seconds, _hhmmss_to_seconds(end))

    if max_seconds <= 0:
        return None

    minutes = max(1, int(math.ceil(max_seconds / 60)))
    return f'{minutes} min'


class RomsListView(APIView):
    permission_classes = (AllowAny,)

    def get(self, request):
        _sync_recordings_from_disk()
        rooms = list(_filter_rooms_queryset(request))
        all_recordings = list(Recording.objects.all().order_by('-created_at'))

        payload = []
        for room in rooms:
            room_recordings = [recording for recording in all_recordings if _recording_matches_room(recording, room)]
            room_participants = _participant_payload_from_room(room)
            recording_participants = _merge_participants(room_recordings)
            participants = _merge_participant_payloads(room_participants, recording_participants)

            recordings_payload = []
            atas_payload = []

            for recording in room_recordings:
                recording_download_url = None
                if recording.file:
                    try:
                        recording_download_url = request.build_absolute_uri(recording.file.url)
                    except Exception:
                        recording_download_url = recording.file.url

                duration_label = _estimate_duration_label(recording)
                recordings_payload.append({
                    'id': f'rec-{recording.id}',
                    'date': _format_datetime_iso8601(recording.created_at),
                    'duration': duration_label,
                    'downloadUrl': recording_download_url,
                })

                if recording.minutes_text or recording.minutes_generated_at or recording.minutes_status == Recording.MINUTES_DONE:
                    ata_download_url = None
                    try:
                        ata_download_url = request.build_absolute_uri(f'/video/api/recordings/{recording.id}/minutes/')
                    except Exception:
                        ata_download_url = f'/video/api/recordings/{recording.id}/minutes/'
                    atas_payload.append({
                        'id': f'ata-{recording.id}',
                        'date': _format_datetime_iso8601(recording.minutes_generated_at or recording.created_at),
                        'duration': duration_label,
                        'downloadUrl': ata_download_url,
                    })

            payload.append({
                'id': str(room.id),
                'name': room.name or None,
                'created_at': _format_datetime_iso8601(room.created_at),
                'participants': participants,
                'donwloads': {
                    'recordings': recordings_payload,
                    'atas': atas_payload,
                },
            })

        return Response(payload)


class RoomViewSet(viewsets.ModelViewSet):
    serializer_class = RoomSerializer

    def get_queryset(self):
        return _filter_rooms_queryset(self.request)


class CouchExampleView(APIView):
    """Example endpoint that creates a document in CouchDB using the client."""

    def post(self, request):
        payload = request.data or {}
        try:
            # lazy import to avoid import-time side-effects
            from video_backend.couchdb_client import create_doc

            result = create_doc(payload)
            return Response({"id": result.get('id')}, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class CouchDocsList(APIView):
    """List CouchDB documents."""

    def get(self, request):
        try:
            from video_backend.couchdb_client import list_docs
            data = list_docs()
            return Response(data)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class CouchDocDetail(APIView):
    """Retrieve, update or delete a CouchDB document by id."""

    def get(self, request, doc_id):
        try:
            from video_backend.couchdb_client import get_doc
            doc = get_doc(doc_id)
            return Response(doc)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_404_NOT_FOUND)

    def put(self, request, doc_id):
        try:
            from video_backend.couchdb_client import update_doc
            payload = request.data or {}
            result = update_doc(doc_id, payload)
            return Response(result)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, doc_id):
        try:
            from video_backend.couchdb_client import delete_doc
            result = delete_doc(doc_id)
            return Response(result)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


@method_decorator(csrf_exempt, name='dispatch')
class RecordingUploadView(APIView):
    parser_classes = (MultiPartParser, FormParser)
    permission_classes = (AllowAny,)

    def post(self, request, format=None):
        room_identifier = (request.data.get('room_id') or request.data.get('room_name') or '').strip()
        resolved_room = _resolve_room_from_identifier(room_identifier, create_if_missing=True) if room_identifier else None
        serializer_data = request.data.copy()
        serializer_data.pop('room_id', None)

        serializer = RecordingSerializer(data=serializer_data)
        if serializer.is_valid():
            recording = serializer.save(
                room=resolved_room,
                room_name=room_identifier or (str(resolved_room.id) if resolved_room else ''),
            )
            enqueue_minutes_generation(str(recording.id))
            payload = serializer.data
            payload['room_id'] = str(recording.room_id) if recording.room_id else None
            payload['minutes_status'] = recording.minutes_status
            payload['minutes_url'] = request.build_absolute_uri(f'/video/api/recordings/{recording.id}/minutes/')
            return Response(payload, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def get(self, request, format=None):
        """List recordings with absolute file URLs.

        Also scans media/recordings/ on disk and auto-registers any .webm/.mp4
        files found there that are not yet in the database, so recordings saved
        directly to the filesystem (e.g. by the Playwright recorder script) are
        always visible via this endpoint.
        """
        # --- sync disk → DB ---
        _sync_recordings_from_disk()

        # --- return full list ---
        qs = _filter_recordings_queryset(request)
        data = []
        for r in qs:
            file_url = r.file.url if r.file else None
            minutes_url = None
            if file_url and request is not None:
                try:
                    file_url = request.build_absolute_uri(file_url)
                except Exception:
                    pass
            if request is not None:
                try:
                    minutes_url = request.build_absolute_uri(f'/video/api/recordings/{r.id}/minutes/')
                except Exception:
                    minutes_url = None
            data.append({
                'id': str(r.id),
                'file': r.file.name if r.file else None,
                'room_id': str(r.room_id) if r.room_id else None,
                'room_name': r.room_name or '',
                'url': file_url,
                'minutes_status': getattr(r, 'minutes_status', None),
                'minutes_url': minutes_url,
                'minutes_generated_at': getattr(r, 'minutes_generated_at', None),
                'created_at': r.created_at,
            })
        return Response(data)


@method_decorator(csrf_exempt, name='dispatch')
class RecordingChunkUploadView(APIView):
    parser_classes = (MultiPartParser, FormParser)
    permission_classes = (AllowAny,)

    def post(self, request, format=None):
        upload_id = request.data.get('upload_id')
        filename = request.data.get('filename') or f"recording-{uuid4().hex}.webm"
        room_name_raw = request.data.get('room_name') or request.data.get('room_id') or ''
        is_last = str(request.data.get('is_last', '')).lower() in {'1', 'true', 'yes'}
        chunk = request.FILES.get('chunk')
        participants_raw = request.data.get('participants', '')

        if not upload_id:
            return Response({'error': 'upload_id é obrigatório'}, status=status.HTTP_400_BAD_REQUEST)

        temp_dir = Path(settings.MEDIA_ROOT) / 'tmp_recordings'
        temp_dir.mkdir(parents=True, exist_ok=True)
        temp_path = temp_dir / f"{upload_id}.part"

        if chunk is not None:
            with open(temp_path, 'ab') as temp_file:
                for piece in chunk.chunks():
                    temp_file.write(piece)

        if not is_last:
            current_size = temp_path.stat().st_size if temp_path.exists() else 0
            return Response({'ok': True, 'upload_id': upload_id, 'size': current_size})

        if not temp_path.exists() or temp_path.stat().st_size == 0:
            return Response({'error': 'nenhum dado recebido para finalizar upload'}, status=status.HTTP_400_BAD_REQUEST)

        safe_name = os.path.basename(str(filename)) or f"recording-{uuid4().hex}.webm"
        room_name_value = _extract_room_name_hint(room_name_raw, safe_name, upload_id)
        resolved_room = _resolve_room_from_identifier(room_name_value, create_if_missing=True) if room_name_value else None
        participants_json = ''
        if participants_raw:
            try:
                parsed = json.loads(participants_raw)
                if isinstance(parsed, list):
                    participants_json = json.dumps(parsed)
            except Exception:
                participants_json = ''

        with open(temp_path, 'rb') as temp_file:
            recording = Recording.objects.create(
                file=File(temp_file, name=safe_name),
                room=resolved_room,
                room_name=room_name_value or (str(resolved_room.id) if resolved_room else ''),
                participants_json=participants_json,
            )

        try:
            if temp_path.exists():
                temp_path.unlink()
        except Exception:
            pass

        file_url = recording.file.url if recording.file else None
        minutes_url = None
        if file_url and request is not None:
            try:
                file_url = request.build_absolute_uri(file_url)
            except Exception:
                pass
        if request is not None:
            try:
                minutes_url = request.build_absolute_uri(f'/video/api/recordings/{recording.id}/minutes/')
            except Exception:
                minutes_url = None

        enqueue_minutes_generation(str(recording.id))

        return Response({
            'id': str(recording.id),
            'file': recording.file.name if recording.file else None,
            'room_id': str(recording.room_id) if recording.room_id else None,
            'room_name': recording.room_name or '',
            'url': file_url,
            'minutes_status': recording.minutes_status,
            'minutes_url': minutes_url,
            'minutes_generated_at': recording.minutes_generated_at,
            'created_at': recording.created_at,
        }, status=status.HTTP_201_CREATED)


class RecordingMinutesView(APIView):
    permission_classes = (AllowAny,)

    def get(self, request, recording_id):
        try:
            recording = Recording.objects.get(id=recording_id)
        except Recording.DoesNotExist:
            return Response({'error': 'gravação não encontrada'}, status=status.HTTP_404_NOT_FOUND)

        file_url = recording.file.url if recording.file else None
        if file_url:
            try:
                file_url = request.build_absolute_uri(file_url)
            except Exception:
                pass

        return Response({
            'id': str(recording.id),
            'recording_url': file_url,
            'minutes_status': recording.minutes_status,
            'minutes_generated_at': recording.minutes_generated_at,
            'minutes_error': recording.minutes_error,
            'minutes_text': recording.minutes_text,
        })


class RoomRecordingStartView(APIView):
    permission_classes = (AllowAny,)

    def post(self, request):
        room_name = request.data.get('room_name')
        started_by = request.data.get('started_by') or request.data.get('client_id') or 'server'
        ok, message, state = start_server_recording(room_name=room_name, started_by=started_by)
        status_code = status.HTTP_200_OK if ok else status.HTTP_409_CONFLICT
        payload = {
            'ok': ok,
            'message': message,
            'room_name': room_name,
        }
        if state is not None:
            payload.update({
                'is_recording': state.is_recording,
                'started_by': state.started_by,
                'started_at': state.started_at,
            })
        return Response(payload, status=status_code)


class RoomRecordingStopView(APIView):
    permission_classes = (AllowAny,)

    def post(self, request):
        room_name = request.data.get('room_name')
        stopped_by = request.data.get('stopped_by') or request.data.get('client_id') or 'server'
        ok, message, state = stop_server_recording(room_name=room_name, stopped_by=stopped_by)
        status_code = status.HTTP_200_OK if ok else status.HTTP_409_CONFLICT
        payload = {
            'ok': ok,
            'message': message,
            'room_name': room_name,
        }
        if state is not None:
            payload.update({
                'is_recording': state.is_recording,
                'started_by': state.started_by,
                'started_at': state.started_at,
            })
        return Response(payload, status=status_code)


class RoomRecordingStatusView(APIView):
    permission_classes = (AllowAny,)

    def get(self, request):
        room_name = request.query_params.get('room_name')
        state = get_room_recording_status(room_name)
        if state is None:
            return Response({
                'room_name': room_name,
                'is_recording': False,
                'started_by': '',
                'started_at': None,
            })

        return Response({
            'room_name': state.room_name,
            'is_recording': state.is_recording,
            'started_by': state.started_by,
            'started_at': state.started_at,
        })


class RoomRecordingCompleteView(APIView):
    permission_classes = (AllowAny,)

    def post(self, request):
        room_name = (request.data.get('room_name') or '').strip()
        room_obj = _resolve_room_from_identifier(room_name, create_if_missing=True) if room_name else None
        recording_payload = request.data.get('recording') or {}
        if not room_name:
            return Response({'error': 'room_name é obrigatório'}, status=status.HTTP_400_BAD_REQUEST)
        if not isinstance(recording_payload, dict):
            return Response({'error': 'recording inválido'}, status=status.HTTP_400_BAD_REQUEST)

        if recording_payload.get('error'):
            notify_recording_ready(room_name, {
                'error': recording_payload.get('error'),
            })
            return Response({'ok': True})

        recording = None
        recording_id = (recording_payload.get('id') or '').strip()
        if recording_id:
            try:
                recording = Recording.objects.filter(id=recording_id).first()
                if recording is not None:
                    changed_fields = []
                    if room_obj is not None and recording.room_id != room_obj.id:
                        recording.room = room_obj
                        changed_fields.append('room')

                    canonical_room_name = str(room_obj.id) if room_obj is not None else room_name
                    if recording.room_name != canonical_room_name:
                        recording.room_name = canonical_room_name
                        changed_fields.append('room_name')

                    if room_obj is not None and not _participants_json_has_entries(recording.participants_json):
                        participants_json = _participants_json_from_room(room_obj)
                        if participants_json:
                            recording.participants_json = participants_json
                            changed_fields.append('participants_json')

                    if changed_fields:
                        recording.save(update_fields=changed_fields)
            except Exception:
                recording = None

        resolved_payload = dict(recording_payload)
        if recording is not None:
            recording_url = ''
            if recording.file:
                try:
                    recording_url = recording.file.url
                except Exception:
                    recording_url = ''

            resolved_payload = {
                'id': str(recording.id),
                'file': recording.file.name if recording.file else None,
                'room_id': str(recording.room_id) if recording.room_id else None,
                'room_name': recording.room_name or room_name,
                'url': recording_url,
                'minutes_status': recording.minutes_status,
                'minutes_url': f'/video/api/recordings/{recording.id}/minutes/',
                'minutes_generated_at': recording.minutes_generated_at,
                'created_at': recording.created_at,
            }

        resolved_payload['url'] = _normalize_relative_client_url(resolved_payload.get('url'))
        default_minutes_url = ''
        resolved_recording_id = resolved_payload.get('id')
        if resolved_recording_id:
            default_minutes_url = f'/video/api/recordings/{resolved_recording_id}/minutes/'
        resolved_payload['minutes_url'] = _normalize_relative_client_url(
            resolved_payload.get('minutes_url') or default_minutes_url
        )

        notify_recording_ready(room_name, resolved_payload)
        return Response({'ok': True})
