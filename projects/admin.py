from django.conf import settings
from django.contrib import admin

from .models import BasicAuth, Environment, Flavor, Project, ProjectLog, ProjectTemplate

admin.site.register(ProjectTemplate)
admin.site.register(Environment)
admin.site.register(ProjectLog)
admin.site.register(BasicAuth)


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "status", "updated_at", "project_template")
    list_filter = ["owner", "status", "project_template"]
    actions = ["update_app_limits"]

    @admin.action(description="Reset app limits")
    def update_app_limits(self, request, queryset):
        queryset.update(apps_per_project=settings.APPS_PER_PROJECT_LIMIT)


@admin.register(Flavor)
class FlavorAdmin(admin.ModelAdmin):
    list_display = ("name", "project", "updated_at")
    list_filter = ["project"]
