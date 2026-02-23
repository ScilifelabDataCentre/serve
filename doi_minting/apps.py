from django.apps import AppConfig


class DoiMintingConfig(AppConfig):  # type: ignore[misc]
    default_auto_field = "django.db.models.BigAutoField"
    name = "doi_minting"
