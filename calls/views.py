from rest_framework import viewsets, status
from rest_framework.views import APIView
from rest_framework.response import Response
from .models import Room, Recording
from .serializers import RoomSerializer
from .serializers import RecordingSerializer
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import AllowAny
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from django.core.files.base import File
from datetime import timezone as datetime_timezone
from pathlib import Path
from uuid import uuid4
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


def _sync_recordings_from_disk():
    recordings_dir = Path(settings.MEDIA_ROOT) / 'recordings'
    recordings_dir.mkdir(parents=True, exist_ok=True)
    known_names = set(Recording.objects.values_list('file', flat=True))
    for fpath in sorted(recordings_dir.iterdir()):
        if fpath.suffix.lower() not in {'.webm', '.mp4', '.mkv'}:
            continue
        relative = f'recordings/{fpath.name}'
        if relative not in known_names:
            try:
                Recording.objects.create(file=relative, room_name='')
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
    if isinstance(raw_participant, dict):
        name = str(raw_participant.get('name', '')).strip()
        if not name:
            return None

        raw_roles = raw_participant.get('roles')
        if isinstance(raw_roles, str):
            roles = [raw_roles]
        elif isinstance(raw_roles, list):
            roles = raw_roles
        else:
            roles = []

        normalized_roles = [str(role).strip() for role in roles if str(role).strip()]

        image_url = raw_participant.get('imageUrl')
        if image_url is None:
            image_url = raw_participant.get('image_url')
        normalized_image_url = str(image_url).strip() if image_url else None

        return {
            'name': name,
            'roles': normalized_roles,
            'imageUrl': normalized_image_url,
        }

    name = str(raw_participant).strip()
    if not name:
        return None
    return {
        'name': name,
        'roles': [],
        'imageUrl': None,
    }


def _merge_participants(recordings):
    participants_by_name = {}

    for recording in recordings:
        for participant in _parse_recording_participants(recording):
            normalized = _normalize_participant(participant)
            if not normalized:
                continue

            participant_key = normalized['name'].casefold()
            current = participants_by_name.get(participant_key)
            if current is None:
                participants_by_name[participant_key] = normalized
                continue

            current_roles = set(current['roles'])
            for role in normalized['roles']:
                if role not in current_roles:
                    current['roles'].append(role)
                    current_roles.add(role)

            if not current.get('imageUrl') and normalized.get('imageUrl'):
                current['imageUrl'] = normalized['imageUrl']

    return list(participants_by_name.values())


def _recording_matches_room(recording, room):
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
        matched_recording_ids = set()

        payload = []
        for room in rooms:
            room_recordings = [recording for recording in all_recordings if _recording_matches_room(recording, room)]
            for recording in room_recordings:
                matched_recording_ids.add(str(recording.id))
            participants = _merge_participants(room_recordings)

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
                        ata_download_url = request.build_absolute_uri(f'/api/recordings/{recording.id}/minutes/')
                    except Exception:
                        ata_download_url = f'/api/recordings/{recording.id}/minutes/'
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

        if len(payload) == 1:
            legacy_unmatched = [
                recording
                for recording in all_recordings
                if str(recording.id) not in matched_recording_ids
            ]
            if legacy_unmatched:
                single_room = payload[0]
                existing_participants = single_room.get('participants') or []
                merged = _merge_participants(legacy_unmatched)
                if merged:
                    participants_by_name = {str(p.get('name', '')).casefold(): p for p in existing_participants if p.get('name')}
                    for participant in merged:
                        participant_name = str(participant.get('name', '')).casefold()
                        if participant_name and participant_name not in participants_by_name:
                            existing_participants.append(participant)
                    single_room['participants'] = existing_participants

                for recording in legacy_unmatched:
                    recording_download_url = None
                    if recording.file:
                        try:
                            recording_download_url = request.build_absolute_uri(recording.file.url)
                        except Exception:
                            recording_download_url = recording.file.url

                    duration_label = _estimate_duration_label(recording)
                    single_room['donwloads']['recordings'].append({
                        'id': f'rec-{recording.id}',
                        'date': _format_datetime_iso8601(recording.created_at),
                        'duration': duration_label,
                        'downloadUrl': recording_download_url,
                    })

                    if recording.minutes_text or recording.minutes_generated_at or recording.minutes_status == Recording.MINUTES_DONE:
                        ata_download_url = None
                        try:
                            ata_download_url = request.build_absolute_uri(f'/api/recordings/{recording.id}/minutes/')
                        except Exception:
                            ata_download_url = f'/api/recordings/{recording.id}/minutes/'
                        single_room['donwloads']['atas'].append({
                            'id': f'ata-{recording.id}',
                            'date': _format_datetime_iso8601(recording.minutes_generated_at or recording.created_at),
                            'duration': duration_label,
                            'downloadUrl': ata_download_url,
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
        serializer = RecordingSerializer(data=request.data)
        if serializer.is_valid():
            recording = serializer.save()
            enqueue_minutes_generation(str(recording.id))
            payload = serializer.data
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
        recordings_dir = Path(settings.MEDIA_ROOT) / 'recordings'
        recordings_dir.mkdir(parents=True, exist_ok=True)
        known_names = set(Recording.objects.values_list('file', flat=True))
        for fpath in sorted(recordings_dir.iterdir()):
            if fpath.suffix.lower() not in {'.webm', '.mp4', '.mkv'}:
                continue
            relative = f'recordings/{fpath.name}'
            if relative not in known_names:
                try:
                    Recording.objects.create(file=relative)
                except Exception:
                    pass  # race condition / duplicate, ignore

        # --- return full list ---
        qs = Recording.objects.all().order_by('-created_at')
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
        room_name_raw = request.data.get('room_name', '')
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
                room_name=room_name_value,
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

        recording_id = (recording_payload.get('id') or '').strip()
        if recording_id:
            try:
                Recording.objects.filter(id=recording_id, room_name='').update(room_name=room_name)
            except Exception:
                pass

        notify_recording_ready(room_name, recording_payload)
        return Response({'ok': True})
