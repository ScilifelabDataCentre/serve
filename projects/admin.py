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
    list_display = ("name", "owner", "status", "updated_at")
    list_filter = ["owner", "status"]


@admin.register(Flavor)
class FlavorAdmin(admin.ModelAdmin):
    list_display = ("name", "project", "updated_at")
    list_filter = ["project"]
