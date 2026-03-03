import os
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny


class TurnConfigView(APIView):
    permission_classes = (AllowAny,)

    def get(self, request):
        """Return ICE servers (STUN + optional TURN from env)."""
        stun_servers = [
            {"urls": "stun:stun.l.google.com:19302"},
            {"urls": "stun:stun1.l.google.com:19302"},
            {"urls": "stun.services.mozilla.com"},
        ]

        ice = [s for s in stun_servers]

        turn_user = os.environ.get('TURN_USER')
        turn_pass = os.environ.get('TURN_PASS')
        public_ip = os.environ.get('PUBLIC_IP')

        if turn_user and turn_pass and public_ip:
            ice.append({
                "urls": [f"turn:{public_ip}:3478"],
                "username": turn_user,
                "credential": turn_pass,
            })

        return Response({"iceServers": ice})
