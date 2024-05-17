import time

from django.contrib import admin, messages
from django.db.models.query import QuerySet

from studio.utils import get_logger

from .helpers import get_URI
from .models import (
    AppCategories,
    Apps,
    AppStatus,
    BaseAppInstance,
    CustomAppInstance,
    DashInstance,
    FilemanagerInstance,
    JupyterInstance,
    NetpolicyInstance,
    RStudioInstance,
    ShinyInstance,
    Subdomain,
    TissuumapsInstance,
    VolumeInstance,
    VSCodeInstance,
)
from .tasks import delete_resource, deploy_resource

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


class BaseAppAdmin(admin.ModelAdmin):
    list_display = ("name", "display_owner", "display_project", "display_status", "display_subdomain", "chart")

    list_filter = ["owner", "project", "app_status__status", "chart"]
    actions = ["redeploy_apps", "deploy_resources", "delete_resources"]

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

    def display_volumes(self, obj):
        if obj.volume is None:
            return "No Volumes"
        elif isinstance(obj.volume, QuerySet):
            return [volume.name for volume in obj.volume.all()]
        else:
            return obj.volume.name
        

    display_volumes.short_description = "Volumes"

    @admin.action(description="(Re)deploy resources")
    def deploy_resources(self, request, queryset):
        success_count = 0
        failure_count = 0

        for instance in queryset:
            instance.set_k8s_values()
            instance.url = get_URI(instance.k8s_values)
            instance.save(update_fields=["k8s_values", "url"])

            deploy_resource.delay(instance.serialize())
            time.sleep(2)
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
            self.message_user(request, f"{success_count} apps successfully (re)deployed.", messages.SUCCESS)
        if failure_count:
            self.message_user(
                request, f"Failed to redeploy {failure_count} apps. Check logs for details.", messages.ERROR
            )

    @admin.action(description="Delete resources")
    def delete_resources(self, request, queryset):
        success_count = 0
        failure_count = 0

        for instance in queryset:
            instance.set_k8s_values()
            delete_resource.delay(instance.serialize())
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
            self.message_user(request, f"{success_count} apps successfully deleted.", messages.SUCCESS)
        if failure_count:
            self.message_user(
                request, f"Failed to delete {failure_count} apps. Check logs for details.", messages.ERROR
            )


@admin.register(BaseAppInstance)
class BaseAppInstanceAdmin(BaseAppAdmin):
    list_display = BaseAppAdmin.list_display + ("display_subclass",)

    def display_subclass(self, obj):
        subclasses = BaseAppInstance.__subclasses__()
        for subclass in subclasses:
            app_type = getattr(obj, subclass.__name__.lower(), None)
            if app_type:
                return app_type.__class__.__name__

    display_subclass.short_description = "Subclass"


@admin.register(RStudioInstance)
class RStudioInstanceAdmin(BaseAppAdmin):
    list_display = BaseAppAdmin.list_display + ("access", "display_volumes")


@admin.register(VSCodeInstance)
class VSCodeInstanceAdmin(BaseAppAdmin):
    list_display = BaseAppAdmin.list_display + ("access", "display_volumes")


@admin.register(JupyterInstance)
class JupyterInstanceAdmin(BaseAppAdmin):
    list_display = BaseAppAdmin.list_display + ("access", "display_volumes")


@admin.register(VolumeInstance)
class VolumeInstanceAdmin(BaseAppAdmin):
    list_display = BaseAppAdmin.list_display + ("display_size",)

    def display_size(self, obj):
        return f"{str(obj.size)} GB"

    display_size.short_description = "Size"


@admin.register(NetpolicyInstance)
class NetpolicyInstanceAdmin(BaseAppAdmin):
    list_display = BaseAppAdmin.list_display


@admin.register(DashInstance)
class DashInstanceAdmin(BaseAppAdmin):
    list_display = BaseAppAdmin.list_display + ("image",)


@admin.register(CustomAppInstance)
class CustomAppInstanceAdmin(BaseAppAdmin):
    list_display = BaseAppAdmin.list_display + (
        "display_volumes",
        "image",
        "port",
        "user_id",
    )


@admin.register(ShinyInstance)
class ShinyInstanceAdmin(BaseAppAdmin):
    list_display = BaseAppAdmin.list_display + (
        "image",
        "port",
    )


@admin.register(TissuumapsInstance)
class TissuumapsInstanceAdmin(BaseAppAdmin):
    list_display = BaseAppAdmin.list_display + ("display_volumes",)


@admin.register(FilemanagerInstance)
class FilemanagerInstanceAdmin(BaseAppAdmin):
    list_display = BaseAppAdmin.list_display + (
        "display_volumes",
        "persistent",
    )


admin.site.register(Subdomain)
admin.site.register(AppCategories)
admin.site.register(AppStatus, AppStatusAdmin)
