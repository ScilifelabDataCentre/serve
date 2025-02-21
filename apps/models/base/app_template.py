from django.db import models


class Apps(models.Model):
    """Essentially app template"""

    user_can_create = models.BooleanField(default=True)
    user_can_edit = models.BooleanField(default=True)
    user_can_delete = models.BooleanField(default=True)
    user_can_see_secrets = models.BooleanField(default=False)
    access = models.CharField(max_length=20, blank=True, null=True, default="public")
    category = models.ForeignKey(
        "AppCategories",
        related_name="apps",
        on_delete=models.CASCADE,
        null=True,
    )
    chart = models.CharField(max_length=512)
    chart_archive = models.FileField(upload_to="apps/", null=True, blank=True)
    created_on = models.DateTimeField(auto_now_add=True)
    description = models.TextField(blank=True, null=True, default="")
    gpu_enabled = models.BooleanField(default=False)
    logo = models.CharField(max_length=512, null=True, blank=True)
    name = models.CharField(max_length=512)
    priority = models.IntegerField(default=100)
    projects = models.ManyToManyField("projects.Project", blank=True)
    revision = models.IntegerField(default=1)
    settings = models.JSONField(blank=True, null=True)
    slug = models.CharField(max_length=512, blank=True, null=True)
    table_field = models.JSONField(blank=True, null=True)
    updated_on = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = (
            "slug",
            "revision",
        )
        verbose_name = "App Template"
        verbose_name_plural = "App Templates"

    def __str__(self):
        return str(self.name) + "({})".format(self.revision)

    def to_dict(self):
        pass
