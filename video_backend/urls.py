from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.views.static import serve
from django.shortcuts import redirect

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('calls.urls')),
    # Serve client static files in development (rooms.html, test_call.html)
    re_path(r'^client/(?P<path>.*)$', serve, {'document_root': str(settings.BASE_DIR / 'client')}),
    # Redirect root to the client rooms page for convenience
    path('', lambda request: redirect('/client/rooms.html')),
    # Helpful shortcuts to open the test client directly
    path('call/', lambda request: redirect('/client/test_call.html')),
    path('call/<str:room>/', lambda request, room: redirect(f'/client/test_call.html?room={room}')),
]
