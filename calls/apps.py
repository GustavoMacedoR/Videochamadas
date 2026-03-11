from django.apps import AppConfig


class CallsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'calls'

    def ready(self):
        from calls.recordings_cleanup import start_recordings_cleanup_scheduler

        start_recordings_cleanup_scheduler()
