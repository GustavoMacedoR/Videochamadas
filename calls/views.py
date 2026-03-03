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
from pathlib import Path
from uuid import uuid4
import os
import json

from .transcription import enqueue_minutes_generation


class RoomViewSet(viewsets.ModelViewSet):
    queryset = Room.objects.all().order_by('-created_at')
    serializer_class = RoomSerializer


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
        """List recordings with absolute file URLs."""
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
                'url': file_url,
                'minutes_status': r.minutes_status,
                'minutes_url': minutes_url,
                'minutes_generated_at': r.minutes_generated_at,
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
        participants_json = ''
        if participants_raw:
            try:
                parsed = json.loads(participants_raw)
                if isinstance(parsed, list):
                    participants_json = json.dumps([str(item) for item in parsed])
            except Exception:
                participants_json = ''

        with open(temp_path, 'rb') as temp_file:
            recording = Recording.objects.create(file=File(temp_file, name=safe_name), participants_json=participants_json)

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
