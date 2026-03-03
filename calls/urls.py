from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import RoomViewSet, CouchExampleView, CouchDocsList, CouchDocDetail, RecordingUploadView, RecordingChunkUploadView
from .turn_view import TurnConfigView

router = DefaultRouter()
router.register(r'rooms', RoomViewSet, basename='room')

urlpatterns = [
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
    path('turn/', TurnConfigView.as_view(), name='turn-config'),
]
