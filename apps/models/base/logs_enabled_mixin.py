from django.db import models


class LogsEnabledMixin(models.Model):
    logs_enabled = models.BooleanField(
        default=True, help_text="Indicates whether logs are activated and visible to the user"
    )

    class Meta:
        abstract = True
