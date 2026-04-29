from django.apps import AppConfig


class AppsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps"

    def ready(self):
        import apps.signals
        from apps.background_tasks.load import register_tasks

        register_tasks()
