from django.contrib import admin, messages

from studio.utils import get_logger

from .models import ShinyInstance, Apps, AppCategories,AppStatus, Subdomain, JupyterInstance, VolumeInstance, DashInstance, CustomAppInstance, NetpolicyInstance, TissuumapsInstance

from .tasks import deploy_resource

logger = get_logger(__name__)


class AppStatusAdmin(admin.ModelAdmin):
    list_display = (
        "status",
        "time",
    )
    list_filter = ["status", "time"]


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


class AbstractAppInstanceAdmin(admin.ModelAdmin):
    list_display = ("name", "display_owner", "display_project", "display_status", "display_subdomain", "chart")

    list_filter = ["owner", "project", "app_status__status", "chart"]
    actions = ["redeploy_apps", "update_chart"]
    

    def display_status(self, obj):
        status_object = obj.app_status
        if status_object:
            return status_object.status
        else: 
            "No status"
    display_status.short_description = "Status"
     
    
    def display_subdomain(self, obj):
        subdomain_object = obj.subdomain
        if subdomain_object:
            return subdomain_object.subdomain
        else: 
            "No Subdomain"
    display_subdomain.short_description = "Subdomain"    

    def display_owner(self, obj):
        return obj.owner.username
    display_owner.short_description = "Owner"    

    def display_project(self, obj):
        return obj.project.name
    display_project.short_description = "Project"    

    @admin.action(description="Redeploy apps")
    def redeploy_apps(self, request, queryset):
        success_count = 0
        failure_count = 0

        for instance in queryset:
            deploy_resource.delay(instance.serialize())
            info_dict = instance.info
            if info_dict:
                success = info_dict["helm"].get("success", False)
                if success:
                    success_count += 1
                else:
                    failure_count += 1
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
                k8s_values = appinstance.k8s_values
                app = Apps.objects.get(slug=k8s_values["app_slug"])
                k8s_values.update({"chart": app.chart})

                # Secondly, update charts for the dependencies
                app_deps = k8s_values.get("apps")
                # Loop through the outer dictionary
                for app_key, app_dict in app_deps.items():
                    # Loop through each project in the projects dictionary
                    for key, details in app_dict.items():
                        slug = details["slug"]
                        app = Apps.objects.get(slug=slug)
                        # Update the chart value
                        details["chart"] = app.chart
                        app_deps[app_key][key] = details
                k8s_values.update({"apps": app_deps})
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

@admin.register(JupyterInstance)
class JupyterInstanceAdmin(AbstractAppInstanceAdmin):
    list_display = AbstractAppInstanceAdmin.list_display + ("access", "display_volumes")
    
    def display_volumes(self, obj):
        return [volume.name for volume in obj.volume.all()]
    display_volumes.short_description = "Volumes"


@admin.register(VolumeInstance)
class VolumeInstanceAdmin(AbstractAppInstanceAdmin):
    list_display = AbstractAppInstanceAdmin.list_display + ("display_size",)
    
    def display_size(self, obj):
        return f"{str(obj.size)} GB"
    display_size.short_description = "Size"
    
@admin.register(NetpolicyInstance)
class NetpolicyInstanceAdmin(AbstractAppInstanceAdmin):
    list_display = AbstractAppInstanceAdmin.list_display

@admin.register(DashInstance)
class DashInstanceAdmin(AbstractAppInstanceAdmin):
    list_display = AbstractAppInstanceAdmin.list_display + ("image",)

@admin.register(CustomAppInstance)
class CustomAppInstanceAdmin(AbstractAppInstanceAdmin):
    list_display = AbstractAppInstanceAdmin.list_display + ("image", "port", "user_id",)

@admin.register(ShinyInstance)
class ShinyInstanceAdmin(AbstractAppInstanceAdmin):
    list_display = AbstractAppInstanceAdmin.list_display + ("image", "port",)
    
@admin.register(TissuumapsInstance)
class TissuumapsInstanceAdmin(AbstractAppInstanceAdmin):
    list_display = AbstractAppInstanceAdmin.list_display

admin.site.register(Subdomain)
admin.site.register(AppCategories)
admin.site.register(AppStatus, AppStatusAdmin)
