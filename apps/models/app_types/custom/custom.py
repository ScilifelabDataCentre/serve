import regex as re
from django.core.exceptions import ValidationError
from django.db import models

from apps.models import AppInstanceManager, BaseAppInstance

from .base import AbstractCustomAppInstance


def validate_default_url_subpath(candidate):
    """
    Validates a custom default url path addition.
    The RegexValidator will raise a ValidationError if the input does not match the regular expression.
    It is up to the caller to handle the raised exception if desired.
    """
    error_message = (
        "Your custom URL subpath is not valid, please correct it. "
        "It must be 1-53 characters long."
        " It can contain only Unicode letters, digits, hyphens"
        " ( - ), forward slashes ( / ), and underscores ( _ )."
        " It cannot start or end with a hyphen ( - ) and "
        "cannot start with a forward slash ( / )."
        " It cannot contain consecutive forward slashes ( // )."
    )

    pattern = r"^(?!-)(?!/)(?!.*//)[\p{Letter}\p{Mark}0-9-/_]{1,53}(?<!-)$|^$"

    if not re.match(pattern, candidate):
        raise ValidationError(error_message)


class CustomAppInstanceManager(AppInstanceManager):
    model_type = "customappinstance"


class CustomAppInstance(AbstractCustomAppInstance, BaseAppInstance):
    default_url_subpath = models.CharField(
        validators=[validate_default_url_subpath], max_length=255, default="", blank=True
    )
    objects = CustomAppInstanceManager()
