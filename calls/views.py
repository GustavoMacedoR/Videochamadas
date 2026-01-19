from rest_framework import viewsets, status
from rest_framework.views import APIView
from rest_framework.response import Response
from .models import Room
from .serializers import RoomSerializer
from .serializers import RecordingSerializer
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import AllowAny
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt


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
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
