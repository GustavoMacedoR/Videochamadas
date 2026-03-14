import logging
import os
import signal
import subprocess
import uuid
import shutil
from pathlib import Path

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import RoomRecordingState

logger = logging.getLogger(__name__)


def _notify_room(room_name, payload):
    channel_layer = get_channel_layer()
    if not channel_layer:
        return
    async_to_sync(channel_layer.group_send)(
        f'call_{room_name}',
        {
            'type': 'signal.message',
            'sender': '',
            'data': payload,
        },
    )


def notify_recording_ready(room_name, recording_payload):
    _notify_room(room_name, {
        'type': 'recording_ready',
        'room_name': room_name,
        'recording': recording_payload,
    })


def _build_room_url(room_name):
    base = os.environ.get('SERVER_CLIENT_BASE_URL')
    if base:
        return f"{base.rstrip('/')}/call/{room_name}/"
    return f"http://127.0.0.1:8000/call/{room_name}/"


def _build_api_base():
    api_base = os.environ.get('SERVER_API_BASE_URL')
    if api_base:
        return api_base.rstrip('/')
    return 'http://127.0.0.1:8000/api'


def _is_pid_alive(pid):
    if not pid:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _cleanup_if_stale(state):
    if state.is_recording and not _is_pid_alive(state.process_pid):
        state.is_recording = False
        state.process_pid = None
        state.process_token = ''
        state.save(update_fields=['is_recording', 'process_pid', 'process_token', 'updated_at'])


def start_server_recording(room_name, started_by='server'):
    room_name = (room_name or '').strip()
    if not room_name:
        return False, 'room_name é obrigatório', None

    with transaction.atomic():
        state, _ = RoomRecordingState.objects.select_for_update().get_or_create(room_name=room_name)
        _cleanup_if_stale(state)
        if state.is_recording:
            return False, 'Já existe gravação ativa nesta sala.', state

        if not shutil.which('node'):
            return False, 'Node.js não encontrado no servidor para iniciar gravação.', state

        token = uuid.uuid4().hex
        upload_id = f'{room_name}-{token}'
        file_name = f'{room_name}-{timezone.now().strftime("%Y%m%d-%H%M%S")}.webm'

        node_script = Path(settings.BASE_DIR) / 'scripts' / 'server_room_recorder.js'
        room_url = _build_room_url(room_name)
        api_base = _build_api_base()
        env = os.environ.copy()
        env.update({
            'ROOM_URL': room_url,
            'API_BASE': api_base,
            'ROOM_NAME': room_name,
            'UPLOAD_ID': upload_id,
            'FILE_NAME': file_name,
            'PARTICIPANTS_JSON': '[]',
            'RECORDER_NAME': 'Gravador',
            'RECORDER_ROLE': 'gravador',
        })

        logger.info(
            'Iniciando gravação: room=%s, room_url=%s, api_base=%s, upload_id=%s, file_name=%s, script=%s',
            room_name, room_url, api_base, upload_id, file_name, node_script,
        )

        # Log to a file so recorder errors are visible
        log_dir = Path(settings.MEDIA_ROOT) / 'recorder_logs'
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file_path = log_dir / f'{room_name}-{timezone.now().strftime("%Y%m%d-%H%M%S")}.log'

        try:
            log_fh = open(log_file_path, 'w')
            process = subprocess.Popen(
                ['node', str(node_script)],
                cwd=str(settings.BASE_DIR),
                env=env,
                stdout=log_fh,
                stderr=log_fh,
            )
        except Exception as exc:
            logger.exception('Falha ao iniciar o processo de gravação: %s', exc)
            return False, 'Falha ao iniciar o processo de gravação no servidor.', state

        logger.info('Processo de gravação iniciado: pid=%s, log=%s', process.pid, log_file_path)

        state.is_recording = True
        state.started_by = started_by or 'server'
        state.process_pid = process.pid
        state.process_token = token
        state.started_at = timezone.now()
        state.save(update_fields=['is_recording', 'started_by', 'process_pid', 'process_token', 'started_at', 'updated_at'])

    _notify_room(room_name, {
        'type': 'recording_started',
        'room_name': room_name,
        'started_by': state.started_by,
        'started_at': state.started_at.isoformat() if state.started_at else None,
    })
    return True, 'Gravação iniciada no servidor.', state


def stop_server_recording(room_name, stopped_by='server'):
    room_name = (room_name or '').strip()
    if not room_name:
        return False, 'room_name é obrigatório', None

    with transaction.atomic():
        try:
            state = RoomRecordingState.objects.select_for_update().get(room_name=room_name)
        except RoomRecordingState.DoesNotExist:
            return False, 'Sala não encontrada.', None

        if not state.is_recording:
            return False, 'Não há gravação ativa nesta sala.', state

        _cleanup_if_stale(state)
        if not state.is_recording:
            return False, 'Gravação já estava encerrada.', state

        pid = state.process_pid
        if pid:
            logger.info('Enviando SIGTERM para processo de gravação: pid=%s, room=%s', pid, room_name)
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError as exc:
                logger.warning('Falha ao enviar SIGTERM para pid=%s: %s', pid, exc)

        state.is_recording = False
        state.process_pid = None
        state.process_token = ''
        state.save(update_fields=['is_recording', 'process_pid', 'process_token', 'updated_at'])

    _notify_room(room_name, {
        'type': 'recording_stopped',
        'room_name': room_name,
        'stopped_by': stopped_by or 'server',
        'stopped_at': timezone.now().isoformat(),
    })
    return True, 'Gravação finalizada no servidor.', state


def get_room_recording_status(room_name):
    room_name = (room_name or '').strip()
    if not room_name:
        return None
    try:
        state = RoomRecordingState.objects.get(room_name=room_name)
        _cleanup_if_stale(state)
        return state
    except RoomRecordingState.DoesNotExist:
        return None
