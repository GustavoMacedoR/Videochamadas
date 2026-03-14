import fcntl
import logging
import os
import shutil
import sys
import threading
import time
from pathlib import Path

from django.conf import settings
from django.db import close_old_connections


LOGGER = logging.getLogger(__name__)
_THREAD = None
_THREAD_LOCK = threading.Lock()


def _as_bool(value, default=False):
    if value is None:
        return default
    return str(value).strip().lower() in {'1', 'true', 'yes', 'on'}


def _cleanup_enabled():
    env_value = os.environ.get('RECORDINGS_AUTO_CLEANUP_ENABLED')
    if env_value is not None:
        return _as_bool(env_value, default=True)
    return bool(getattr(settings, 'RECORDINGS_AUTO_CLEANUP_ENABLED', True))


def _cleanup_interval_seconds():
    env_value = os.environ.get('RECORDINGS_AUTO_CLEANUP_INTERVAL_MINUTES')
    default_value = getattr(settings, 'RECORDINGS_AUTO_CLEANUP_INTERVAL_MINUTES', 30)
    raw_value = env_value if env_value is not None else default_value
    try:
        minutes = int(raw_value)
    except (TypeError, ValueError):
        minutes = 30
    minutes = max(1, minutes)
    return minutes * 60


def _lock_file_path():
    configured_path = os.environ.get('RECORDINGS_AUTO_CLEANUP_LOCK_FILE')
    if configured_path:
        return Path(configured_path)
    return Path('/tmp/videochamadas-recordings-cleanup.lock')


def _should_skip_scheduler_start():
    if len(sys.argv) > 1 and sys.argv[1] == 'runserver' and os.environ.get('RUN_MAIN') != 'true':
        return True
    return False


def _max_age_seconds():
    env_value = os.environ.get('RECORDINGS_MAX_AGE_HOURS')
    default_value = getattr(settings, 'RECORDINGS_MAX_AGE_HOURS', 168)  # 7 days
    raw_value = env_value if env_value is not None else default_value
    try:
        hours = int(raw_value)
    except (TypeError, ValueError):
        hours = 168
    return max(1, hours) * 3600


def _clear_old_recordings():
    from calls.models import Recording
    from django.utils import timezone as dj_timezone
    import datetime

    max_age = _max_age_seconds()
    cutoff = dj_timezone.now() - datetime.timedelta(seconds=max_age)

    recordings_dir = Path(settings.MEDIA_ROOT) / 'recordings'
    recordings_dir.mkdir(parents=True, exist_ok=True)

    # Delete old DB records and their files
    old_recordings = Recording.objects.filter(
        file__startswith='recordings/',
        created_at__lt=cutoff,
    )
    deleted_paths = 0
    deleted_records = 0
    for rec in old_recordings:
        try:
            if rec.file:
                file_path = Path(settings.MEDIA_ROOT) / str(rec.file)
                if file_path.is_file():
                    file_path.unlink()
                    deleted_paths += 1
        except Exception:
            LOGGER.exception('Falha ao remover arquivo de gravação: %s', rec.file)
        rec.delete()
        deleted_records += 1

    # Clean orphaned files on disk (no DB record) older than max_age
    known_files = set(Recording.objects.values_list('file', flat=True))
    now_ts = time.time()
    for fpath in recordings_dir.iterdir():
        relative = f'recordings/{fpath.name}'
        if relative in known_files:
            continue
        try:
            if fpath.is_file() or fpath.is_symlink():
                file_age = now_ts - fpath.stat().st_mtime
                if file_age > max_age:
                    fpath.unlink()
                    deleted_paths += 1
            elif fpath.is_dir():
                shutil.rmtree(fpath, ignore_errors=True)
                deleted_paths += 1
        except Exception:
            LOGGER.exception('Falha ao remover caminho de gravação órfão: %s', fpath)

    return deleted_paths, deleted_records


def _run_cleanup_if_due(interval_seconds):
    lock_path = _lock_file_path()
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    with open(lock_path, 'a+', encoding='utf-8') as lock_file:
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return False

        lock_file.seek(0)
        raw_last_run = lock_file.read().strip()
        now = time.time()

        try:
            last_run = float(raw_last_run)
        except (TypeError, ValueError):
            last_run = 0.0

        if last_run <= 0:
            lock_file.seek(0)
            lock_file.truncate()
            lock_file.write(str(now))
            lock_file.flush()
            os.fsync(lock_file.fileno())
            return False

        if (now - last_run) < interval_seconds:
            return False

        deleted_paths, deleted_records = _clear_old_recordings()
        if deleted_paths or deleted_records:
            LOGGER.info(
                'Limpeza automática de gravações concluída: %s caminho(s) removido(s), %s registro(s) removido(s).',
                deleted_paths,
                deleted_records,
            )

        lock_file.seek(0)
        lock_file.truncate()
        lock_file.write(str(now))
        lock_file.flush()
        os.fsync(lock_file.fileno())
        return True


def _scheduler_loop():
    interval_seconds = _cleanup_interval_seconds()
    poll_seconds = min(60, max(5, interval_seconds // 6))

    LOGGER.info('Limpeza automática de gravações habilitada (intervalo: %s segundos).', interval_seconds)

    while True:
        try:
            close_old_connections()
            _run_cleanup_if_due(interval_seconds)
        except Exception:
            LOGGER.exception('Erro durante a execução da limpeza automática de gravações.')
        finally:
            close_old_connections()
        time.sleep(poll_seconds)


def start_recordings_cleanup_scheduler():
    if not _cleanup_enabled():
        return
    if _should_skip_scheduler_start():
        return

    global _THREAD
    with _THREAD_LOCK:
        if _THREAD is not None and _THREAD.is_alive():
            return
        _THREAD = threading.Thread(target=_scheduler_loop, name='recordings-cleanup-scheduler', daemon=True)
        _THREAD.start()
