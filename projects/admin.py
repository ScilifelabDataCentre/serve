from django.conf import settings
from django.contrib import admin

from .models import (
    BasicAuth,
    Environment,
    Flavor,
    PersistentVolumeMountPath,
    Project,
    ProjectLog,
    ProjectTemplate,
)

admin.site.register(ProjectTemplate)
admin.site.register(ProjectLog)
admin.site.register(BasicAuth)


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    search_fields = ("name", "owner__username", "project_template__name", "status")
    list_display = ("name", "owner", "status", "updated_at", "project_template")
    list_filter = ["owner", "status", "project_template"]
    actions = ["update_app_limits"]
    readonly_fields = ["created_at"]
    autocomplete_fields = ("privileged_users",)

    @admin.action(description="Reset app limits")
    def update_app_limits(self, request, queryset):
        queryset.update(apps_per_project=settings.APPS_PER_PROJECT_LIMIT)


@admin.register(Flavor)
class FlavorAdmin(admin.ModelAdmin):
    search_fields = ("name", "project__name")
    list_display = ("name", "project", "updated_at")
    list_filter = ["project"]


@admin.register(Environment)
class EnvironmentAdmin(admin.ModelAdmin):
    search_fields = ("name", "project__name")
    list_display = ("name", "project", "updated_at")
    list_filter = ["project"]


@admin.register(PersistentVolumeMountPath)
class PVCMountPathAdmin(admin.ModelAdmin):
    search_fields = ("volume__name", "mount_path")
    list_display = ("volume__project__name", "volume__subdomain", "volume", "mount_path", "volume__size")
    list_filter = ["volume__project__name"]
