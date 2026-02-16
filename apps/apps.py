from django.apps import AppConfig


class AppsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps"

    def ready(self):
        import logging

        import apps.signals
        from doi_minting.services.keywords_service import VocabularyMemoryService

        logger = logging.getLogger(__name__)
        logger.info("Initializing Invenio keywords service...")
        VocabularyMemoryService()
        logger.info("Invenio keywords service ready")
