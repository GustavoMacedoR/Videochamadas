from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.views.static import serve
from django.shortcuts import redirect

urlpatterns = [
    path('video/admin/', admin.site.urls),
    path('video/api/', include('calls.urls')),
    # Serve client static files in development (rooms.html, test_call.html) under /video/
    re_path(r'^video/client/(?P<path>.*)$', serve, {'document_root': str(settings.BASE_DIR / 'client')}),
    # Redirect root to the client rooms page for convenience (prefixed)
    path('', lambda request: redirect('/video/client/rooms.html')),
    # Helpful shortcuts to open the test client directly (prefixed)
    path('video/call/', lambda request: redirect('/video/client/test_call.html')),
    path('video/call/<str:room>/', lambda request, room: redirect(f'/video/client/test_call.html?room={room}')),
]

# Serve media files during development when DEBUG=True
if settings.DEBUG:
    urlpatterns += [
        re_path(r'^video/media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
    ]
