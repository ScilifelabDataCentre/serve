from django.apps import AppConfig


class CommonConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "common"

    def ready(self):
        """
        This function is used to register the signal handlers.

        See
        `Django documentation <https://docs.djangoproject.com/en/4.2/ref/applications/#django.apps.AppConfig.ready>`_
        for more information.
        """
        import common.signals
