import json
import os
import threading
from datetime import datetime

from django.db import close_old_connections
from django.utils import timezone


_MODEL = None
_MODEL_LOCK = threading.Lock()


def _seconds_to_hhmmss(total_seconds):
    total_seconds = max(0, int(total_seconds))
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def _load_whisper_model():
    global _MODEL
    if _MODEL is not None:
        return _MODEL
    with _MODEL_LOCK:
        if _MODEL is not None:
            return _MODEL
        import whisper

        model_name = os.environ.get('WHISPER_MODEL', 'base')
        _MODEL = whisper.load_model(model_name)
    return _MODEL


def _parse_participants(participants_json):
    if not participants_json:
        return []
    try:
        data = json.loads(participants_json)
    except Exception:
        return []
    if isinstance(data, list):
        return [str(item).strip() for item in data if str(item).strip()]
    return []


def _build_minutes_text(recording, segments):
    participants = _parse_participants(recording.participants_json)
    if not participants:
        participants = ['Usuário 1', 'Usuário 2']

    conversation_lines = []
    speaker_index = 0
    last_end = None

    for segment in segments:
        start = float(segment.get('start', 0.0) or 0.0)
        end = float(segment.get('end', start) or start)
        text = (segment.get('text') or '').strip()
        if not text:
            continue

        if last_end is not None and (start - last_end) > 1.2:
            speaker_index = (speaker_index + 1) % len(participants)

        speaker = participants[speaker_index]
        start_label = _seconds_to_hhmmss(start)
        end_label = _seconds_to_hhmmss(end)
        conversation_lines.append(f"- [{start_label}-{end_label}] {speaker}: {text}")
        last_end = end

    if not conversation_lines:
        return "Nenhuma fala foi detectada na gravação."

    key_points = []
    for line in conversation_lines[:12]:
        content = line.split(':', 1)[1].strip() if ':' in line else line
        key_points.append(f"- {content}")

    created_at = timezone.localtime(recording.created_at).strftime('%Y-%m-%d %H:%M:%S')
    ata = [
        '# Ata da Chamada',
        '',
        f'- Gravação: {recording.file.name}',
        f'- Data/hora: {created_at}',
        f'- Participantes detectados: {", ".join(participants)}',
        '',
        '## Resumo',
        *key_points,
        '',
        '## Transcrição por participante (estimada)',
        *conversation_lines,
        '',
        '_Observação: identificação de participante é estimada com base em segmentação temporal do áudio._',
    ]
    return '\n'.join(ata)


def _process_recording_minutes(recording_id):
    close_old_connections()
    from .models import Recording

    try:
        recording = Recording.objects.get(id=recording_id)
    except Recording.DoesNotExist:
        return

    try:
        recording.minutes_status = Recording.MINUTES_PROCESSING
        recording.minutes_error = ''
        recording.save(update_fields=['minutes_status', 'minutes_error'])

        model = _load_whisper_model()
        result = model.transcribe(recording.file.path, language='pt', task='transcribe', fp16=False)
        segments = result.get('segments') or []
        minutes_text = _build_minutes_text(recording, segments)

        recording.minutes_text = minutes_text
        recording.minutes_status = Recording.MINUTES_DONE
        recording.minutes_generated_at = timezone.now()
        recording.minutes_error = ''
        recording.save(update_fields=['minutes_text', 'minutes_status', 'minutes_generated_at', 'minutes_error'])
    except Exception as exc:
        recording.minutes_status = Recording.MINUTES_FAILED
        recording.minutes_error = str(exc)
        recording.minutes_generated_at = timezone.now()
        recording.save(update_fields=['minutes_status', 'minutes_error', 'minutes_generated_at'])
    finally:
        close_old_connections()


def enqueue_minutes_generation(recording_id):
    worker = threading.Thread(target=_process_recording_minutes, args=(recording_id,), daemon=True)
    worker.start()
