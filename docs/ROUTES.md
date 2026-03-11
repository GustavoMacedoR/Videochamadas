# Documentação completa de endpoints (HTTP + WebSocket)

Esta documentação cobre **todos os endpoints expostos pela aplicação** neste workspace, com exemplos de uso e payloads reais do código.

## Swagger UI

- Spec OpenAPI: `/client/openapi.yaml`
- Interface Swagger: `/client/swagger.html`

## 1) Convenções e bases

- Todas as rotas HTTP usam barra final (`/`).
- A API em Django está montada em `api/` (ex.: `http://127.0.0.1:8000/api/...`).
- No ambiente com proxy/reverse-proxy deste projeto, costuma-se usar prefixo `/video` (ex.: `https://seu-dominio/video/api/...`).
- Não há autenticação obrigatória implementada nesses endpoints (vários usam `AllowAny`).

Exemplo de variáveis para testes:

```bash
# Local (runserver puro)
BASE_HTTP="http://127.0.0.1:8000"
API_BASE="$BASE_HTTP/api"

# Produção/proxy típico do projeto
# BASE_HTTP="https://seu-dominio"
# API_BASE="$BASE_HTTP/video/api"
```

---

## 2) Endpoints HTTP da aplicação (fora de `/api`)

### 2.1 `GET /admin/`
Admin padrão do Django.

```bash
curl -i "$BASE_HTTP/admin/"
```

### 2.2 `GET /client/<path>`
Serve arquivos estáticos da pasta `client/` (ex.: `rooms.html`, `test_call.html`) em desenvolvimento.

```bash
curl -i "$BASE_HTTP/client/rooms.html"
curl -i "$BASE_HTTP/client/test_call.html"
```

### 2.3 `GET /`
Redireciona para `/client/rooms.html`.

```bash
curl -i "$BASE_HTTP/"
```

Resposta típica:

```http
HTTP/1.1 302 Found
Location: /client/rooms.html
```

### 2.4 `GET /call/`
Redireciona para `/client/test_call.html`.

```bash
curl -i "$BASE_HTTP/call/"
```

### 2.5 `GET /call/<room>/`
Redireciona para `/client/test_call.html?room=<room>`.

```bash
curl -i "$BASE_HTTP/call/sala-1/"
```

Resposta típica:

```http
HTTP/1.1 302 Found
Location: /client/test_call.html?room=sala-1
```

### 2.6 `GET /video/media/<path>` (somente `DEBUG=True`)
Serve mídia (gravações) durante desenvolvimento.

```bash
curl -i "$BASE_HTTP/video/media/recordings/exemplo.webm"
```

---

## 3) API REST (`/api/`)

## 3.0 `GET /api/`
Root da API do DRF (lista recursos registrados no router).

```bash
curl -s "$API_BASE/" | jq
```

Resposta típica:

```json
{
  "rooms": "http://127.0.0.1:8000/api/rooms/"
}
```

### 3.1 Rooms

#### 3.1.0 `GET /api/roms/`
Retorna salas no formato usado pelo cliente de histórico/downloads.

`participants` é alimentado por participantes que entraram na call via WebSocket (`join/chat/raise_hand/lower_hand`) e também por metadados das gravações da própria sala.

Query params opcionais (mesmos filtros de `rooms`):
- `name`: filtro `icontains` no nome.
- `id`: filtro `icontains` no UUID.
- `date`: filtro por data de criação (`YYYY-MM-DD`).

```bash
curl -s "$API_BASE/roms/" | jq
```

Resposta `200` (exemplo):

```json
[
  {
    "id": "203c13ed-4f61-448f-b326-f947f6644fe0",
    "name": "Turma A",
    "created_at": "2026-03-05T13:10:00.000Z",
    "participants": [
      {
        "name": "Ana Souza",
        "roles": ["ALUNO"],
        "imageUrl": null
      }
    ],
    "donwloads": {
      "recordings": [
        {
          "id": "rec-7e6dc0d5-6e08-4892-bdb6-5984a2e50d72",
          "date": "2026-03-05T13:45:00.000Z",
          "duration": "35 min",
          "downloadUrl": "http://127.0.0.1:8000/video/media/recordings/turma-a-20260305-134500.webm"
        }
      ],
      "atas": [
        {
          "id": "ata-7e6dc0d5-6e08-4892-bdb6-5984a2e50d72",
          "date": "2026-03-05T14:10:00.000Z",
          "duration": "35 min",
          "downloadUrl": "http://127.0.0.1:8000/api/recordings/7e6dc0d5-6e08-4892-bdb6-5984a2e50d72/minutes/"
        }
      ]
    }
  }
]
```

#### 3.1.1 `GET /api/rooms/`
Lista salas ordenadas por `created_at` desc.

Query params opcionais:
- `name`: filtro `icontains` no nome.
- `id`: filtro `icontains` no UUID.
- `date`: filtro por data de criação (`YYYY-MM-DD`).

```bash
curl -s "$API_BASE/rooms/?name=turma&id=a1b2&date=2026-03-05" | jq
```

Resposta `200` (exemplo):

```json
[
  {
    "id": "203c13ed-4f61-448f-b326-f947f6644fe0",
    "name": "Turma A",
    "created_at": "2026-03-05T13:10:00Z"
  }
]
```

#### 3.1.2 `POST /api/rooms/`
Cria sala.

Body JSON:

```json
{
  "name": "Turma A"
}
```

```bash
curl -s -X POST "$API_BASE/rooms/" \
  -H "Content-Type: application/json" \
  -d '{"name":"Turma A"}' | jq
```

Resposta `201`:

```json
{
  "id": "203c13ed-4f61-448f-b326-f947f6644fe0",
  "name": "Turma A",
  "created_at": "2026-03-05T13:10:00Z"
}
```

#### 3.1.3 `GET /api/rooms/<uuid>/`
Busca sala por id.

```bash
curl -s "$API_BASE/rooms/203c13ed-4f61-448f-b326-f947f6644fe0/" | jq
```

Resposta `200`: objeto da sala.

#### 3.1.4 `PUT /api/rooms/<uuid>/`
Atualiza sala inteira.

```bash
curl -s -X PUT "$API_BASE/rooms/203c13ed-4f61-448f-b326-f947f6644fe0/" \
  -H "Content-Type: application/json" \
  -d '{"name":"Turma A - Atualizada"}' | jq
```

Resposta `200`: objeto atualizado.

#### 3.1.5 `PATCH /api/rooms/<uuid>/`
Atualização parcial.

```bash
curl -s -X PATCH "$API_BASE/rooms/203c13ed-4f61-448f-b326-f947f6644fe0/" \
  -H "Content-Type: application/json" \
  -d '{"name":"Novo nome"}' | jq
```

#### 3.1.6 `DELETE /api/rooms/<uuid>/`
Remove sala.

```bash
curl -i -X DELETE "$API_BASE/rooms/203c13ed-4f61-448f-b326-f947f6644fe0/"
```

Resposta `204 No Content`.

---

### 3.2 CouchDB helpers

> Observação: esses endpoints dependem da configuração/saúde do CouchDB (`video_backend.couchdb_client`).

#### 3.2.1 `POST /api/couch/example/`
Cria documento no CouchDB com o payload enviado.

```bash
curl -s -X POST "$API_BASE/couch/example/" \
  -H "Content-Type: application/json" \
  -d '{"type":"nota","titulo":"Teste"}' | jq
```

Resposta `201`:

```json
{
  "id": "f3d2b4..."
}
```

Erro típico `500`:

```json
{
  "error": "mensagem do erro"
}
```

#### 3.2.2 `GET /api/couch/docs/`
Lista documentos do CouchDB.

```bash
curl -s "$API_BASE/couch/docs/" | jq
```

Resposta `200`: estrutura retornada por `list_docs()`.

#### 3.2.3 `GET /api/couch/docs/<doc_id>/`

```bash
curl -s "$API_BASE/couch/docs/abc123/" | jq
```

Resposta `200`: documento.

Erro `404`:

```json
{"error":"mensagem do erro"}
```

#### 3.2.4 `PUT /api/couch/docs/<doc_id>/`

```bash
curl -s -X PUT "$API_BASE/couch/docs/abc123/" \
  -H "Content-Type: application/json" \
  -d '{"titulo":"Atualizado"}' | jq
```

Resposta `200`: retorno de `update_doc(...)`.

Erro `400`:

```json
{"error":"mensagem do erro"}
```

#### 3.2.5 `DELETE /api/couch/docs/<doc_id>/`

```bash
curl -s -X DELETE "$API_BASE/couch/docs/abc123/" | jq
```

Resposta `200`: retorno de `delete_doc(...)`.

Erro `400`:

```json
{"error":"mensagem do erro"}
```

---

### 3.3 Recordings

Status possíveis de `minutes_status` no modelo:
- `pending`
- `processing`
- `done`
- `failed`

#### 3.3.1 `POST /api/recordings/`
Upload simples de gravação (multipart).

Campos multipart:
- `file` (obrigatório)
- `room_id` (opcional; UUID da sala, prioridade sobre `room_name`)
- `room_name` (opcional; identificador da sala para vincular a gravação)
- `participants_json` (opcional, string JSON)

```bash
curl -s -X POST "$API_BASE/recordings/" \
  -F "file=@/caminho/gravacao.webm" \
  -F 'participants_json=["Professor","Aluno"]' | jq
```

Resposta `201` (exemplo):

```json
{
  "id": "8f53e700-d117-4980-b7ca-e7d57465f004",
  "file": "http://127.0.0.1:8000/video/media/recordings/gravacao.webm",
  "participants_json": "[\"Professor\",\"Aluno\"]",
  "minutes_status": "pending",
  "minutes_text": "",
  "minutes_error": "",
  "minutes_generated_at": null,
  "created_at": "2026-03-05T13:25:15.742345Z",
  "minutes_url": "http://127.0.0.1:8000/video/api/recordings/8f53e700-d117-4980-b7ca-e7d57465f004/minutes/"
}
```

Erro `400`: erros de validação do serializer (ex.: falta de arquivo).

#### 3.3.2 `GET /api/recordings/`
Lista gravações. Também sincroniza arquivos existentes em `media/recordings/` para o banco.

```bash
curl -s "$API_BASE/recordings/" | jq
```

Resposta `200` (exemplo):

```json
[
  {
    "id": "8f53e700-d117-4980-b7ca-e7d57465f004",
    "file": "recordings/gravacao.webm",
    "url": "http://127.0.0.1:8000/video/media/recordings/gravacao.webm",
    "minutes_status": "processing",
    "minutes_url": "http://127.0.0.1:8000/video/api/recordings/8f53e700-d117-4980-b7ca-e7d57465f004/minutes/",
    "minutes_generated_at": null,
    "created_at": "2026-03-05T13:25:15.742345Z"
  }
]
```

#### 3.3.3 `POST /api/recordings/chunk/`
Upload em partes (chunked upload).

Campos multipart:
- `upload_id` (obrigatório)
- `filename` (opcional; padrão `recording-<uuid>.webm`)
- `room_id` (opcional; UUID da sala, prioridade sobre `room_name`)
- `room_name` (opcional; recomendado para vincular corretamente à sala no histórico)
- `is_last` (opcional: `1|true|yes` para finalizar)
- `chunk` (arquivo; obrigatório nas partes intermediárias)
- `participants` (opcional; JSON array em string, usado na finalização)

**Parte intermediária (`is_last=0`)**

```bash
curl -s -X POST "$API_BASE/recordings/chunk/" \
  -F "upload_id=sala-1-tokenxyz" \
  -F "filename=sala-1.webm" \
  -F "is_last=0" \
  -F "chunk=@/tmp/parte-001.bin" | jq
```

Resposta `200`:

```json
{
  "ok": true,
  "upload_id": "sala-1-tokenxyz",
  "size": 524288
}
```

**Finalização (`is_last=1`)**

```bash
curl -s -X POST "$API_BASE/recordings/chunk/" \
  -F "upload_id=sala-1-tokenxyz" \
  -F "filename=sala-1.webm" \
  -F "is_last=1" \
  -F 'participants=["Professor","Aluno"]' | jq
```

Resposta `201`:

```json
{
  "id": "8f53e700-d117-4980-b7ca-e7d57465f004",
  "file": "recordings/sala-1.webm",
  "url": "http://127.0.0.1:8000/video/media/recordings/sala-1.webm",
  "minutes_status": "pending",
  "minutes_url": "http://127.0.0.1:8000/video/api/recordings/8f53e700-d117-4980-b7ca-e7d57465f004/minutes/",
  "minutes_generated_at": null,
  "created_at": "2026-03-05T13:28:10.102000Z"
}
```

Erros comuns `400`:

```json
{"error":"upload_id é obrigatório"}
```

```json
{"error":"nenhum dado recebido para finalizar upload"}
```

#### 3.3.4 `GET /api/recordings/<recording_id>/minutes/`
Retorna o estado e conteúdo da ata/transcrição gerada em background.

```bash
curl -s "$API_BASE/recordings/8f53e700-d117-4980-b7ca-e7d57465f004/minutes/" | jq
```

Resposta `200`:

```json
{
  "id": "8f53e700-d117-4980-b7ca-e7d57465f004",
  "recording_url": "http://127.0.0.1:8000/video/media/recordings/sala-1.webm",
  "minutes_status": "done",
  "minutes_generated_at": "2026-03-05T13:31:44.881002Z",
  "minutes_error": "",
  "minutes_text": "# Ata da Chamada\n..."
}
```

Erro `404`:

```json
{"error":"gravação não encontrada"}
```

#### 3.3.5 `POST /api/recordings/server/start/`
Solicita início da gravação server-side para uma sala.

Body JSON:

```json
{
  "room_name": "sala-1",
  "started_by": "cliente-abc"
}
```

(`started_by` pode ser omitido; fallback para `client_id` ou `"server"`)

```bash
curl -s -X POST "$API_BASE/recordings/server/start/" \
  -H "Content-Type: application/json" \
  -d '{"room_name":"sala-1","started_by":"cliente-abc"}' | jq
```

Sucesso `200`:

```json
{
  "ok": true,
  "message": "Gravação iniciada no servidor.",
  "room_name": "sala-1",
  "is_recording": true,
  "started_by": "cliente-abc",
  "started_at": "2026-03-05T13:35:22.511159Z"
}
```

Conflito `409` (ex.: já gravando / erro de pré-condição):

```json
{
  "ok": false,
  "message": "Já existe gravação ativa nesta sala.",
  "room_name": "sala-1",
  "is_recording": true,
  "started_by": "cliente-abc",
  "started_at": "2026-03-05T13:35:22.511159Z"
}
```

#### 3.3.6 `POST /api/recordings/server/stop/`
Solicita parada da gravação server-side de uma sala.

Body JSON:

```json
{
  "room_name": "sala-1",
  "stopped_by": "cliente-abc"
}
```

(`stopped_by` pode ser omitido; fallback para `client_id` ou `"server"`)

```bash
curl -s -X POST "$API_BASE/recordings/server/stop/" \
  -H "Content-Type: application/json" \
  -d '{"room_name":"sala-1","stopped_by":"cliente-abc"}' | jq
```

Sucesso `200`:

```json
{
  "ok": true,
  "message": "Gravação finalizada no servidor.",
  "room_name": "sala-1",
  "is_recording": false,
  "started_by": "cliente-abc",
  "started_at": "2026-03-05T13:35:22.511159Z"
}
```

Conflito `409` (ex.: sem gravação ativa):

```json
{
  "ok": false,
  "message": "Não há gravação ativa nesta sala.",
  "room_name": "sala-1"
}
```

#### 3.3.7 `GET /api/recordings/server/status/?room_name=<room>`
Consulta estado da gravação da sala.

```bash
curl -s "$API_BASE/recordings/server/status/?room_name=sala-1" | jq
```

Resposta `200` (com estado):

```json
{
  "room_name": "sala-1",
  "is_recording": true,
  "started_by": "cliente-abc",
  "started_at": "2026-03-05T13:35:22.511159Z"
}
```

Resposta `200` (sem estado cadastrado):

```json
{
  "room_name": "sala-1",
  "is_recording": false,
  "started_by": "",
  "started_at": null
}
```

#### 3.3.8 `POST /api/recordings/server/complete/`
Endpoint de callback usado pelo gravador server-side para notificar que a gravação está pronta (ou falhou).

Body JSON:

```json
{
  "room_name": "sala-1",
  "recording": {
    "id": "8f53e700-d117-4980-b7ca-e7d57465f004",
    "url": "http://127.0.0.1:8000/video/media/recordings/sala-1.webm",
    "minutes_url": "http://127.0.0.1:8000/video/api/recordings/8f53e700-d117-4980-b7ca-e7d57465f004/minutes/"
  }
}
```

```bash
curl -s -X POST "$API_BASE/recordings/server/complete/" \
  -H "Content-Type: application/json" \
  -d '{"room_name":"sala-1","recording":{"id":"8f53e700-d117-4980-b7ca-e7d57465f004"}}' | jq
```

Resposta `200`:

```json
{"ok": true}
```

Erros `400`:

```json
{"error":"room_name é obrigatório"}
```

```json
{"error":"recording inválido"}
```

---

### 3.4 TURN / ICE

#### 3.4.1 `GET /api/turn/`
Retorna configuração ICE para WebRTC.

```bash
curl -s "$API_BASE/turn/" | jq
```

Resposta `200` sem TURN configurado:

```json
{
  "iceServers": [
    {"urls": "stun:stun.l.google.com:19302"},
    {"urls": "stun:stun1.l.google.com:19302"},
    {"urls": "stun.services.mozilla.com"}
  ]
}
```

Resposta `200` com TURN (se `TURN_USER`, `TURN_PASS`, `PUBLIC_IP` definidos):

```json
{
  "iceServers": [
    {"urls": "stun:stun.l.google.com:19302"},
    {"urls": "stun:stun1.l.google.com:19302"},
    {"urls": "stun.services.mozilla.com"},
    {
      "urls": ["turn:203.0.113.10:3478"],
      "username": "turn-user",
      "credential": "turn-pass"
    }
  ]
}
```

---

## 4) Endpoint WebSocket

## 4.1 Conexão

- URL: `ws://<host>/ws/calls/<room_name>/`
- Em HTTPS, use `wss://`.
- Sem autenticação no consumer atual.

Exemplo em JavaScript:

```javascript
const ws = new WebSocket('ws://127.0.0.1:8000/ws/calls/sala-1/');
ws.onopen = () => ws.send(JSON.stringify({ type: 'join', client_id: 'cliente-abc' }));
```

## 4.2 Mensagens cliente → servidor

### a) `join`

```json
{"type":"join","client_id":"cliente-abc"}
```

### b) `offer`

```json
{"type":"offer","sdp":"...","to":"peer-1","from":"cliente-abc"}
```

### c) `answer`

```json
{"type":"answer","sdp":"...","to":"peer-1","from":"cliente-abc"}
```

### d) `candidate`

```json
{"type":"candidate","candidate":{"candidate":"..."},"to":"peer-1","from":"cliente-abc"}
```

### e) `chat`

```json
{"type":"chat","name":"Gustavo","message":"Olá"}
```

> O servidor limita `name` a 80 caracteres e `message` a 1000.

### f) `raise_hand`

```json
{"type":"raise_hand","client_id":"cliente-abc","name":"Gustavo"}
```

### g) `lower_hand`

```json
{"type":"lower_hand","client_id":"cliente-abc"}
```

## 4.3 Mensagens servidor → clientes

### a) Broadcast de sinalização
Mensagens não tratadas especificamente (`offer`, `answer`, `candidate`, `join`, etc.) são retransmitidas ao grupo **sem eco para o remetente**.

### b) Chat (`type: chat`)
Enviado para os demais clientes da sala (sem eco para quem enviou):

```json
{"type":"chat","name":"Gustavo","message":"Olá"}
```

### c) Fila de fala
`raise_hand` gera:

```json
{"type":"hand_raise","client_id":"cliente-abc","name":"Gustavo"}
```

`lower_hand` gera:

```json
{"type":"hand_lower","client_id":"cliente-abc"}
```

> Esses eventos são enviados para todos (incluindo remetente) para manter fila sincronizada.

### d) Eventos de gravação server-side

Quando inicia:

```json
{
  "type": "recording_started",
  "room_name": "sala-1",
  "started_by": "cliente-abc",
  "started_at": "2026-03-05T13:35:22.511159+00:00"
}
```

Quando para:

```json
{
  "type": "recording_stopped",
  "room_name": "sala-1",
  "stopped_by": "cliente-abc",
  "stopped_at": "2026-03-05T13:40:04.220001+00:00"
}
```

Quando gravação fica pronta (ou falha):

```json
{
  "type": "recording_ready",
  "room_name": "sala-1",
  "recording": {
    "id": "8f53e700-d117-4980-b7ca-e7d57465f004",
    "url": "http://127.0.0.1:8000/video/media/recordings/sala-1.webm",
    "minutes_url": "http://127.0.0.1:8000/video/api/recordings/8f53e700-d117-4980-b7ca-e7d57465f004/minutes/"
  }
}
```

Exemplo de falha:

```json
{
  "type": "recording_ready",
  "room_name": "sala-1",
  "recording": {
    "error": "Falha ao finalizar gravação no servidor."
  }
}
```

---

## 5) Resumo rápido de todos os endpoints

### HTTP

- `GET /admin/`
- `GET /client/<path>`
- `GET /`
- `GET /call/`
- `GET /call/<room>/`
- `GET /video/media/<path>` (somente `DEBUG=True`)
- `GET /api/`
- `GET|POST /api/rooms/`
- `GET|PUT|PATCH|DELETE /api/rooms/<uuid>/`
- `POST /api/couch/example/`
- `GET /api/couch/docs/`
- `GET|PUT|DELETE /api/couch/docs/<doc_id>/`
- `GET|POST /api/recordings/`
- `POST /api/recordings/chunk/`
- `GET /api/recordings/<recording_id>/minutes/`
- `POST /api/recordings/server/start/`
- `POST /api/recordings/server/stop/`
- `GET /api/recordings/server/status/`
- `POST /api/recordings/server/complete/`
- `GET /api/turn/`

### WebSocket

- `WS /ws/calls/<room_name>/`
