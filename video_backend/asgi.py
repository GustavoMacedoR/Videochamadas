import os

from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'video_backend.settings')

import calls.routing

application = ProtocolTypeRouter({
    'http': get_asgi_application(),
    'websocket': URLRouter(calls.routing.websocket_urlpatterns),
})
