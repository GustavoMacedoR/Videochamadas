# API Routes Documentation

Este documento descreve apenas as rotas HTTP e WebSocket da aplicação, com métodos, payloads e exemplos de retorno.

---

## Base paths
- API base: `/api/`
- Media (dev): `/media/`
- Client (dev): `/client/rooms.html`, `/client/test_call.html`
- WebSocket signaling base: `ws://<host>/ws/calls/<room_name>/`

---

## Endpoints HTTP

### Rooms
- GET /api/rooms/
  - Descrição: Lista salas (ordenadas por `created_at` desc).
  - Resposta 200 (exemplo):
  ```json
  [
    {"id":"<uuid>", "name":"Sala A", "created_at":"2026-01-01T12:00:00Z"},
    ...
  ]
  ```

- POST /api/rooms/
  - Payload (JSON):
  ```json
  {
    "name": "Nome opcional"
  }
  ```
  - Resposta 201 (exemplo):
  ```json
  {"id":"<uuid>", "name":"Nome opcional", "created_at":"..."}
  ```

- GET /api/rooms/{id}/
  - Descrição: Retorna detalhes da sala.
  - Resposta 200: objeto com `id`, `name`, `created_at`.

- PUT/PATCH /api/rooms/{id}/
  - Atualiza a sala. Payload como no POST; responde 200 com o objeto atualizado.

- DELETE /api/rooms/{id}/
  - Elimina a sala. Resposta 204 (sem conteúdo) em caso de sucesso.

---

### Recordings
- POST /api/recordings/
  - Descrição: Upload de gravação (multipart/form-data).
  - Form field: `file` (arquivo, ex: `.webm`).
  - Resposta 201 (exemplo):
  ```json
  {"id":"<uuid>", "file":"recordings/recording-123.webm", "created_at":"..."}
  ```
  - Observação: endpoint permite `AllowAny` e é `csrf_exempt` para facilitar uploads de clientes.

- GET /api/recordings/
  - Descrição: Lista gravações salvas.
  - Resposta 200 (exemplo):
  ```json
  [
    {"id":"<uuid>","file":"recordings/rec-1.webm","url":"https://host/media/recordings/rec-1.webm","created_at":"..."},
    ...
  ]
  ```

---

### TURN / ICE configuration
- GET /api/turn/
  - Descrição: Retorna uma lista `iceServers` (STUNs públicos e opcional TURN configurado por variáveis de ambiente).
  - Resposta 200 (exemplo):
  ```json
  {"iceServers":[{"urls":"stun:stun.l.google.com:19302"}, {"urls":"stun:stun1.l.google.com:19302"}, ...]}
  ```

---

### CouchDB helpers (quando habilitado)
- POST /api/couch/example/
  - Cria um documento no CouchDB com o payload JSON enviado.
  - Resposta 201 (exemplo):
  ```json
  {"id":"<couch_doc_id>"}
  ```

- GET /api/couch/docs/
  - Lista documentos do CouchDB.

- GET /api/couch/docs/{doc_id}/
  - Recupera documento por id.

- PUT /api/couch/docs/{doc_id}/
  - Atualiza documento por id.

- DELETE /api/couch/docs/{doc_id}/
  - Remove documento por id.

---

## WebSocket signaling
- URL: `ws://<host>/ws/calls/<room_name>/`
- Protocolo: JSON via WebSocket. O `CallConsumer` encaminha mensagens recebidas para todos os membros do grupo (exceto o remetente).
- Mensagens: formato JSON livre; usadas mensagens típicas de sinalização WebRTC:
  - Join/announce: `{"type":"join","client_id":"..."}`
  - Offer: `{"type":"offer","sdp":"...","to":"peerId","from":"clientId"}`
  - Answer: `{"type":"answer","sdp":"...","to":"peerId","from":"clientId"}`
  - Candidate: `{"type":"candidate","candidate":{...},"to":"peerId","from":"clientId"}`

---

## Observações gerais
- Em desenvolvimento Django pode servir `/media/` e `/client/` (páginas estáticas), mas em produção recomenda-se que Nginx sirva `/static/` e `/media/` diretamente.
- A documentação acima foca apenas nas rotas e seus contratos (métodos, payloads e exemplos de retorno).

---

*Arquivo gerado automaticamente.*
