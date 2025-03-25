import json
from datetime import datetime, timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import serializers
from django.db import models
from django.db.models import Case, CharField, F, Q, Value, When

from apps.models.base.app_template import Apps
from apps.models.base.k8s_user_app_status import K8sUserAppStatus
from apps.models.base.subdomain import Subdomain
from projects.models import Flavor, Project
from studio.utils import get_logger

logger = get_logger(__name__)

USER_ACTION_STATUS_CHOICES = [
    ("Creating", "Creating"),
    ("Changing", "Changing"),
    ("Deleting", "Deleting"),
    ("SystemDeleting", "SystemDeleting"),
    ("Redeploying", "Redeploying"),
]


def get_status_defs():
    status_success = settings.APPS_STATUS_SUCCESS
    status_warning = settings.APPS_STATUS_WARNING
    return status_success, status_warning


status_success, status_warning = get_status_defs()


class AppInstanceManager(models.Manager):
    model_type = "appinstance"

    def annotate_with_app_status(self):
        """
        Define and add a reusable, chainable annotation app_status.
        The atn prefix stands for annotation and clarifies that this value is computed on the fly.
        This repeats the logic of the class method convert_to_app_status below and is
        therefore not DRY. However the implementation details are too different to be reused.
        """
        return self.get_queryset().annotate(
            atn_app_status=Case(
                When(latest_user_action="Deleting", then=Value("Deleted")),
                When(latest_user_action="SystemDeleting", then=Value("Deleted")),
                When(
                    k8s_user_app_status__status__in=["CrashLoopBackOff", "ErrImagePull", "PostStartHookError"],
                    then=Value("Error"),
                ),
                When(
                    latest_user_action__in=["Creating", "Changing"],
                    k8s_user_app_status__status="NotFound",
                    then=Value("Error (NotFound)"),
                ),
                When(
                    latest_user_action__in=["Creating", "Changing"],
                    k8s_user_app_status__status="Running",
                    then=Value("Running"),
                ),
                When(
                    latest_user_action="Creating",
                    k8s_user_app_status__status__in=["ContainerCreating", "PodInitializing", ""],
                    then=Value("Creating"),
                ),
                When(
                    latest_user_action="Changing",
                    k8s_user_app_status__status__in=["ContainerCreating", "PodInitializing", ""],
                    then=Value("Changing"),
                ),
                default=Value("Unknown"),
                output_field=CharField(),
            )
        )

    def get_app_instances_not_deleted(self):
        """A queryset returning all user apps excluding Deleted apps."""
        return self.annotate_with_app_status().exclude(atn_app_status="Deleted")

    def get_app_instances_of_project_filter(self, user, project, include_deleted=False, deleted_time_delta=None):
        q = Q()

        if not include_deleted:
            if deleted_time_delta is None:
                q &= ~Q(atn_app_status="Deleted")
            else:
                time_threshold = datetime.now() - timedelta(minutes=deleted_time_delta)
                q &= ~Q(atn_app_status="Deleted") | Q(deleted_on__gte=time_threshold)

        if hasattr(self.model, "access"):
            q &= Q(owner=user) | Q(
                access__in=(
                    ["project", "public", "private", "link"] if user.is_superuser else ["project", "public", "link"]
                )
            )
        else:
            q &= Q(owner=user)

        q &= Q(project=project)

        return q

    def get_app_instances_of_project(
        self,
        user,
        project,
        filter_func=None,
        order_by=None,
        limit=None,
        override_default_filter=False,
    ):
        if order_by is None:
            order_by = "-created_on"

        if filter_func is None:
            return (
                self.annotate_with_app_status()
                .filter(self.get_app_instances_of_project_filter(user=user, project=project))
                .order_by(order_by)[:limit]
            )

        if override_default_filter:
            return self.filter(filter_func).order_by(order_by)[:limit]

        return (
            self.annotate_with_app_status()
            .filter(self.get_app_instances_of_project_filter(user=user, project=project))
            .filter(filter_func)
            .order_by(order_by)[:limit]
        )

    def user_can_create(self, user, project, app_slug):
        apps_per_project = {} if project.apps_per_project is None else project.apps_per_project

        limit = apps_per_project[app_slug] if app_slug in apps_per_project else None
        app = Apps.objects.get(slug=app_slug)

        if not app.user_can_create:
            return False

        num_of_app_instances = (
            self.annotate_with_app_status()
            .filter(
                ~Q(atn_app_status="Deleted"),
                app__slug=app_slug,
                project=project,
            )
            .count()
        )

        has_perm = user.has_perm(f"apps.add_{self.model_type}")
        return limit is None or limit > num_of_app_instances or has_perm

    def user_can_edit(self, user, project, app_slug):
        app = Apps.objects.get(slug=app_slug)
        return app.user_can_edit or user.has_perm(f"apps.change_{self.model_type}")


class BaseAppInstance(models.Model):
    objects = AppInstanceManager()

    app = models.ForeignKey(Apps, on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_related")
    chart = models.CharField(
        max_length=512,
    )
    created_on = models.DateTimeField(auto_now_add=True)
    deleted_on = models.DateTimeField(null=True, blank=True)
    info = models.JSONField(blank=True, null=True)
    # model_dependencies = models.ManyToManyField("models.Model", blank=True)
    name = models.CharField(max_length=512, default="app_name")
    owner = models.ForeignKey(
        get_user_model(),
        on_delete=models.CASCADE,
        related_name="%(class)s",
        null=True,
    )
    k8s_values = models.JSONField(blank=True, null=True)
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="%(class)s",
    )
    flavor = models.ForeignKey(Flavor, on_delete=models.RESTRICT, related_name="%(class)s", null=True, blank=True)
    subdomain = models.OneToOneField(
        Subdomain, on_delete=models.SET_NULL, related_name="%(class)s", null=True, blank=True
    )

    latest_user_action = models.CharField(max_length=15, default="Creating", choices=USER_ACTION_STATUS_CHOICES)
    k8s_user_app_status = models.OneToOneField(
        K8sUserAppStatus, on_delete=models.RESTRICT, related_name="%(class)s", null=True, blank=True
    )

    # 20241216: Refactoring of app status.
    # Break connection to model AppStatus and deprecate AppStatus
    # The model AppStatus and related FK app_status is retained for historical reasons
    # app_status = models.OneToOneField(AppStatus, on_delete=models.RESTRICT, related_name="%(class)s", null=True)

    # Get the computed, dynamic app status value
    def get_app_status(self) -> str:
        """Model function exposing the computed app status value."""
        # This model function replaces the old app_status field and related AppStatus model.
        if self.k8s_user_app_status is None:
            k8s_user_app_status = None
        else:
            k8s_user_app_status = self.k8s_user_app_status.status

        status = BaseAppInstance.convert_to_app_status(self.latest_user_action, k8s_user_app_status)
        if status.lower() == "unknown":
            logger.warn(
                f"Invalid input to convert_to_app_status for app {self}. No match for \
                    {self.latest_user_action}, {k8s_user_app_status}"
            )
        return status

    def get_status_group(self) -> str:
        """Get the status group from the app status."""
        status = self.get_app_status()
        group = "success" if status in status_success else "warning" if status in status_warning else "danger"
        return group

    url = models.URLField(blank=True, null=True)
    updated_on = models.DateTimeField(auto_now=True)
    upload_size = models.PositiveIntegerField(default=100, help_text="Max upload size in MB")

    class Meta:
        permissions = [("can_access_app", "Can access app service")]
        verbose_name = "# BASE APP INSTANCE"
        verbose_name_plural = "# BASE APP INSTANCES"

    def __str__(self):
        return f"{self.name}-{self.owner}-{self.app.name}-{self.project}"

    def get_k8s_values(self):
        k8s_values = dict(
            name=self.name,
            appname=self.subdomain.subdomain if self.subdomain else "deleted",
            project=dict(name=self.project.name, slug=self.project.slug),
            service=dict(
                name=(self.subdomain.subdomain if self.subdomain else "deleted") + "-" + self.app.slug,
            ),
            **self.subdomain.to_dict() if self.subdomain else {},
            **self.flavor.to_dict(self.app.gpu_enabled) if self.flavor else {},
            storageClass=settings.STORAGECLASS,
            namespace=settings.NAMESPACE,
            release=self.subdomain.subdomain if self.subdomain else "deleted",  # This is legacy and should be changed
            ingress=dict(clientMaxBodySize=f"{self.upload_size}M"),
        )

        # Add global values
        k8s_values["global"] = dict(
            domain=settings.DOMAIN,
            auth_domain=settings.AUTH_DOMAIN,
            protocol=settings.AUTH_PROTOCOL,
        )
        return k8s_values

    def set_k8s_values(self):
        self.k8s_values = self.get_k8s_values()

    def serialize(self):
        return json.loads(serializers.serialize("json", [self]))[0]

    @staticmethod
    def convert_to_app_status(latest_user_action: str, k8s_user_app_status: str) -> str:
        """Converts latest user action and k8s pod status to app status"""
        match latest_user_action, k8s_user_app_status:
            case "Deleting", _:
                return "Deleted"
            case "SystemDeleting", _:
                return "Deleted"
            case "Creating", "ContainerCreating" | "PodInitializing":
                return "Creating"
            case "Changing", "ContainerCreating" | "PodInitializing":
                return "Changing"
            case _, "NotFound":
                return "Error (NotFound)"
            case _, "CrashLoopBackOff" | "ErrImagePull" | "PostStartHookError":
                return "Error"
            case _, "Running":
                return "Running"
            case "Creating", _:
                return "Creating"
            case "Changing", _:
                return "Changing"
            case _, _:
                logger.debug(
                    f"Invalid input to convert_to_app_status. No match for {latest_user_action}, {k8s_user_app_status}"
                )
                return "Unknown"

        raise ValueError("Invalid input")
