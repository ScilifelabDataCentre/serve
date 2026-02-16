from django.apps import AppConfig


class DoiMintingConfig(AppConfig):
    default_auto_field: str = 'django.db.models.BigAutoField'
    name: str = 'doi_minting'