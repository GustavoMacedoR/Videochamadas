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

Para gravação no servidor (fora de Docker), instale também:

```bash
npm install
npx playwright install chromium
```

Endpoints úteis:
- API Rooms: `/video/api/rooms/` (criar/listar)
- WebSocket signaling: `ws://<host>/ws/call/<room_name>/`
- Upload de gravação: `/video/api/recordings/chunk/`
- Ata da gravação: `/video/api/recordings/<recording_id>/minutes/`
- Iniciar gravação no servidor: `POST /video/api/recordings/server/start/`
- Parar gravação no servidor: `POST /video/api/recordings/server/stop/`
- Status da gravação da sala: `GET /video/api/recordings/server/status/?room_name=<sala>`

Observações:
- Configuração atual usa o backend em memória do Channels (não precisa de Redis).
- Para produção/escala, configure `channels_redis` em `CHANNEL_LAYERS`.
- A ata é gerada em background com Whisper após finalizar o upload da gravação.
- Para produção com Docker, mantenha `ffmpeg` e a dependência `openai-whisper` instaladas (já configuradas neste projeto).
- A gravação agora é controlada pelo servidor e existe bloqueio por sala: se alguém já iniciou gravação, outro participante não consegue iniciar até a gravação ser encerrada.
- O backend notifica todos os participantes via WebSocket quando a gravação inicia/encerra (`recording_started` e `recording_stopped`).
