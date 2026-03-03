from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    # use /ws/calls/ to avoid colliding with an existing /ws/ proxy
    re_path(r'ws/calls/(?P<room_name>[^/]+)/$', consumers.CallConsumer.as_asgi()),
]
