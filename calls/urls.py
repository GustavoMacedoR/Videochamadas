from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import RoomViewSet, RomsListView, CouchExampleView, CouchDocsList, CouchDocDetail, RecordingUploadView, RecordingChunkUploadView, RecordingMinutesView, RecordingMinutesPDFView, RoomRecordingStartView, RoomRecordingStopView, RoomRecordingStatusView, RoomRecordingCompleteView
from .turn_view import TurnConfigView

router = DefaultRouter()
router.register(r'rooms', RoomViewSet, basename='room')

urlpatterns = [
    path('roms', RomsListView.as_view(), name='roms-list-no-slash'),
    path('roms/', RomsListView.as_view(), name='roms-list'),
    path('', include(router.urls)),
    path('couch/example/', CouchExampleView.as_view(), name='couch-example'),
]

urlpatterns += [
    path('couch/docs/', CouchDocsList.as_view(), name='couch-docs-list'),
    path('couch/docs/<str:doc_id>/', CouchDocDetail.as_view(), name='couch-doc-detail'),
]

urlpatterns += [
    path('recordings/', RecordingUploadView.as_view(), name='recording-upload'),
    path('recordings/chunk/', RecordingChunkUploadView.as_view(), name='recording-upload-chunk'),
    path('recordings/<uuid:recording_id>/minutes/', RecordingMinutesView.as_view(), name='recording-minutes'),
    path('recordings/<uuid:recording_id>/minutes/pdf/', RecordingMinutesPDFView.as_view(), name='recording-minutes-pdf'),
    path('recordings/server/start/', RoomRecordingStartView.as_view(), name='recording-server-start'),
    path('recordings/server/stop/', RoomRecordingStopView.as_view(), name='recording-server-stop'),
    path('recordings/server/status/', RoomRecordingStatusView.as_view(), name='recording-server-status'),
    path('recordings/server/complete/', RoomRecordingCompleteView.as_view(), name='recording-server-complete'),
    path('turn/', TurnConfigView.as_view(), name='turn-config'),
]
