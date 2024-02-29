from django.conf import settings
from django.contrib import admin

from .models import (
    S3,
    BasicAuth,
    Environment,
    Flavor,
    MLFlow,
    Project,
    ProjectLog,
    ProjectTemplate,
    ReleaseName,
)

admin.site.register(ProjectTemplate)
# admin.site.register(Project)
admin.site.register(Environment)
# admin.site.register(Flavor)
admin.site.register(ProjectLog)
admin.site.register(S3)
admin.site.register(MLFlow)
admin.site.register(BasicAuth)
admin.site.register(ReleaseName)


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "status", "updated_at", "project_template")
    list_filter = ["owner", "status", "project_template"]
    actions = ["update_app_limits", "update_project_template"]

    @admin.action(description="Reset app limits")
    def update_app_limits(self, request, queryset):
        queryset.update(apps_per_project=settings.APPS_PER_PROJECT_LIMIT)

    # 2024-02-16 - This was added as a temporary method to simplify adding a project template to a project
    # Should be removed if all projects have a linked template.
    @admin.action(description="Change project template to default")
    def update_project_template(self, request, queryset):
        project_template = ProjectTemplate.objects.get(slug="blank")
        queryset.update(project_template=project_template)


@admin.register(Flavor)
class FlavorAdmin(admin.ModelAdmin):
    list_display = ("name", "project", "updated_at")
    list_filter = ["project"]
