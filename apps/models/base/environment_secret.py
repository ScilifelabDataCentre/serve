from django.db import models

from apps.environment_variables import (
    validate_approved_secret_keys,
    validate_kubernetes_secret_name,
)


class AppEnvironmentSecret(models.Model):
    """Approval to import a Kubernetes Secret into a project's apps."""

    project = models.ForeignKey("projects.Project", on_delete=models.CASCADE, related_name="app_environment_secrets")
    name = models.CharField(
        "Kubernetes Secret name",
        max_length=253,
        validators=[validate_kubernetes_secret_name],
        help_text="Existing Secret in the application namespace; no Secret contents are stored here.",
    )
    keys = models.JSONField(
        default=list,
        blank=True,
        validators=[validate_approved_secret_keys],
        help_text="Optional key names for individual selection; whole-Secret access is available with this approval.",
    )

    class Meta:
        constraints = [models.UniqueConstraint(fields=["project", "name"], name="unique_project_app_secret")]
        ordering = ["name"]
        verbose_name = "app Secret approval"
        verbose_name_plural = "app Secret approvals"

    def __str__(self):
        return self.name
