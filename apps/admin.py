from django.contrib import admin, messages

from studio.utils import get_logger

from .models import AppCategories, AppInstance, Apps, AppStatus, ResourceData, JupyterInstance, Subdomain, VolumeInstance
from .tasks import deploy_resource

logger = get_logger(__name__)


class AppsAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "user_can_create",
        "user_can_edit",
        "user_can_delete",
        "slug",
    )
    list_filter = ("user_can_create",)


admin.site.register(Apps, AppsAdmin)


class AppInstanceAdmin(admin.ModelAdmin):
    list_display = ("name", "display_owner", "display_project", "state", "access", "app", "display_chart")

    list_filter = ["owner", "project", "state"]
    actions = ["redeploy_apps", "update_chart"]

    def display_owner(self, obj):
        return obj.owner.username

    def display_project(self, obj):
        return obj.project.name

    def display_chart(self, obj):
        return obj.parameters.get("chart", "No chart")

    @admin.action(description="Redeploy apps")
    def redeploy_apps(self, request, queryset):
        success_count = 0
        failure_count = 0

        for appinstance in queryset:
            result = deploy_resource(appinstance.pk)
            if result.returncode == 0:
                success_count += 1
            else:
                failure_count += 1

        if success_count:
            self.message_user(request, f"{success_count} apps successfully redeployed.", messages.SUCCESS)
        if failure_count:
            self.message_user(
                request, f"Failed to redeploy {failure_count} apps. Check logs for details.", messages.ERROR
            )

    @admin.action(description="Update helm chart definition in parameters")
    def update_chart(self, request, queryset):
        success_count = 0
        failure_count = 0
        for appinstance in queryset:
            # First, update charts for the app
            try:
                parameters = appinstance.parameters
                app = Apps.objects.get(slug=parameters["app_slug"])
                parameters.update({"chart": app.chart})

                # Secondly, update charts for the dependencies
                app_deps = parameters.get("apps")
                # Loop through the outer dictionary
                for app_key, app_dict in app_deps.items():
                    # Loop through each project in the projects dictionary
                    for key, details in app_dict.items():
                        slug = details["slug"]
                        app = Apps.objects.get(slug=slug)
                        # Update the chart value
                        details["chart"] = app.chart
                        app_deps[app_key][key] = details
                parameters.update({"apps": app_deps})
                appinstance.save(update_fields=["parameters"])
                success_count += 1
            except Exception as e:
                logger.error(f"Failed to update app {appinstance.name}. Error: {e}")
                failure_count += 1
        if success_count:
            self.message_user(request, f"{success_count} apps successfully updated.", messages.SUCCESS)
        if failure_count:
            self.message_user(
                request, f"Failed to update {failure_count} apps. Check logs for details.", messages.ERROR
            )


class AppStatusAdmin(admin.ModelAdmin):
    list_display = (
        "appinstance",
        "status_type",
        "time",
    )

    list_filter = ["appinstance", "status_type", "time"]


admin.site.register(JupyterInstance)
admin.site.register(VolumeInstance)
admin.site.register(Subdomain)
admin.site.register(AppCategories)
admin.site.register(ResourceData)
admin.site.register(AppStatus)#, AppStatusAdmin)
