import time

from django.contrib import admin, messages
from django.db.models.query import QuerySet
from django.utils import timezone

from projects.models import PersistentVolumeMountPath
from studio.utils import get_logger

from .constants import AppActionOrigin
from .helpers import get_URI, set_linkonly_reminder_date
from .models import (
    AppCategories,
    Apps,
    AppStatus,
    BaseAppInstance,
    CustomAppInstance,
    DashInstance,
    DepictioInstance,
    FilemanagerInstance,
    GradioInstance,
    JupyterInstance,
    K8sUserAppStatus,
    MLFlowInstance,
    NetpolicyInstance,
    RStudioInstance,
    ShinyInstance,
    StreamlitInstance,
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
        "user_can_see_secrets",
        "slug",
    )
    list_filter = ("user_can_create",)


admin.site.register(Apps, AppsAdmin)


class K8sUserAppStatusAdmin(admin.ModelAdmin):
    list_display = (
        "status",
        "time",
    )
    list_filter = ["status", "time"]


class BaseAppAdmin(admin.ModelAdmin):
    search_fields = (
        "name",
        "owner__username",
        "project__name",
        "subdomain__subdomain",
        "k8s_user_app_status__status",
        "chart",
    )
    list_display = (
        "name",
        "display_owner",
        "display_project",
        "display_status",
        "display_subdomain",
        "chart",
        "upload_size",
    )
    readonly_fields = ("id", "created_on")
    list_filter = ["owner", "project", "k8s_user_app_status__status", "chart"]
    actions = ["redeploy_apps", "deploy_resources", "delete_resources", "set_linkonly_reminder_dates"]

    def display_status(self, obj):
        try:
            return obj.get_app_status()
        except Exception as err:
            logger.warn("Error getting app status: %s", err)
            return "No status"

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
            instance.url = get_URI(instance)
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
            # Set latest_user_action to Deleting
            # This hides the app from the user UI
            instance.latest_user_action = "Deleting"
            instance.deleted_on = timezone.now()
            instance.save(update_fields=["latest_user_action", "deleted_on"])
            delete_resource.delay(instance.serialize(), AppActionOrigin.USER.value)
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

    @admin.action(description="Set new dates for reminders of Link permission apps")
    def set_linkonly_reminder_dates(self, request, queryset):
        """
        Sets the reminder date for the selected apps with Link permission (access) to some time in the
        future as defined in set_linkonly_reminder_date()
        """
        linkonly_changed_count = 0

        for instance in queryset:
            if (
                instance.latest_user_action not in ["Deleting", "SystemDeleting"]
                and hasattr(instance, "access")
                and instance.access == "link"
            ):
                set_linkonly_reminder_date(instance)
                linkonly_changed_count += 1
                instance.save(update_fields=["reminder_date_linkonly_privacy"])

        if linkonly_changed_count:
            self.message_user(
                request,
                f"Successfully set new reminder dates for {linkonly_changed_count} apps with Link permission.",
                messages.SUCCESS,
            )
        else:
            self.message_user(
                request, "There was not a single app with Link permission among the selected apps.", messages.ERROR
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


class VolumeMountPathsInline(admin.StackedInline):
    model = PersistentVolumeMountPath
    extra = 0
    show_change_link = True
    can_delete = True
    verbose_name = "Volume Mount Path"


@admin.register(VolumeInstance)
class VolumeInstanceAdmin(BaseAppAdmin):
    inlines = (VolumeMountPathsInline,)
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
    list_filter = BaseAppAdmin.list_filter + [
        "access",
    ]


@admin.register(MLFlowInstance)
class MLFlowAppInstanceAdmin(BaseAppAdmin):
    # list any fields that you want be listed in the admin pannel.
    list_display = BaseAppAdmin.list_display


@admin.register(CustomAppInstance)
class CustomAppInstanceAdmin(BaseAppAdmin):
    list_display = BaseAppAdmin.list_display + (
        "display_volumes",
        "image",
        "port",
        "user_id",
    )
    list_filter = BaseAppAdmin.list_filter + [
        "access",
    ]


@admin.register(ShinyInstance)
class ShinyInstanceAdmin(BaseAppAdmin):
    list_display = BaseAppAdmin.list_display + (
        "display_volumes",
        "image",
        "port",
    )
    list_filter = BaseAppAdmin.list_filter + [
        "access",
    ]


@admin.register(TissuumapsInstance)
class TissuumapsInstanceAdmin(BaseAppAdmin):
    list_display = BaseAppAdmin.list_display + ("display_volumes",)
    list_filter = BaseAppAdmin.list_filter + [
        "access",
    ]


@admin.register(FilemanagerInstance)
class FilemanagerInstanceAdmin(BaseAppAdmin):
    list_display = BaseAppAdmin.list_display + (
        "display_volumes",
        "persistent",
    )


@admin.register(GradioInstance)
class GradioInstanceAdmin(BaseAppAdmin):
    list_display = BaseAppAdmin.list_display + (
        "display_volumes",
        "image",
        "port",
        "user_id",
    )
    list_filter = BaseAppAdmin.list_filter + [
        "access",
    ]


@admin.register(StreamlitInstance)
class StreamlitInstanceAdmin(BaseAppAdmin):
    list_display = BaseAppAdmin.list_display + (
        "display_volumes",
        "image",
        "port",
        "user_id",
    )
    list_filter = BaseAppAdmin.list_filter + [
        "access",
    ]


class SubdomainAdmin(admin.ModelAdmin):
    list_display = (
        "subdomain",
        "project__name",
    )
    search_fields = ("subdomain", "project__name")
    list_filter = ("subdomain", "project")


@admin.register(DepictioInstance)
class DepictioInstanceAdmin(BaseAppAdmin):
    list_display = BaseAppAdmin.list_display


admin.site.register(Subdomain, SubdomainAdmin)
admin.site.register(AppCategories)
admin.site.register(AppStatus, AppStatusAdmin)
admin.site.register(K8sUserAppStatus, K8sUserAppStatusAdmin)
