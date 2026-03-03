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
- API Rooms: `/video/api/rooms/` (criar/listar)
- WebSocket signaling: `ws://<host>/ws/call/<room_name>/`
- Upload de gravação: `/video/api/recordings/chunk/`
- Ata da gravação: `/video/api/recordings/<recording_id>/minutes/`

Observações:
- Configuração atual usa o backend em memória do Channels (não precisa de Redis).
- Para produção/escala, configure `channels_redis` em `CHANNEL_LAYERS`.
- A ata é gerada em background com Whisper após finalizar o upload da gravação.
- Para produção com Docker, mantenha `ffmpeg` e a dependência `openai-whisper` instaladas (já configuradas neste projeto).
