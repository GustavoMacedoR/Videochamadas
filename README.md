# Backend Django para Videochamadas

Estrutura mínima de backend para sinalização de WebRTC usando Django + Channels.

Passos rápidos para executar:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

Endpoints úteis:
- API Rooms: `/api/rooms/` (criar/listar)
- WebSocket signaling: `ws://<host>/ws/call/<room_name>/`

Observações:
- Configuração atual usa o backend em memória do Channels (não precisa de Redis).
- Para produção/escala, configure `channels_redis` em `CHANNEL_LAYERS`.
