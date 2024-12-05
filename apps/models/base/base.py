import json
from datetime import datetime, timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import serializers
from django.db import models
from django.db.models import Q

from apps.models.base.app_status import AppStatus
from apps.models.base.app_template import Apps
from apps.models.base.subdomain import Subdomain
from projects.models import Flavor, Project


class AppInstanceManager(models.Manager):
    model_type = "appinstance"

    def get_app_instances_of_project_filter(self, user, project, include_deleted=False, deleted_time_delta=None):
        q = Q()

        if not include_deleted:
            if deleted_time_delta is None:
                q &= ~Q(app_status__status="Deleted")
            else:
                time_threshold = datetime.now() - timedelta(minutes=deleted_time_delta)
                q &= ~Q(app_status__status="Deleted") | Q(deleted_on__gte=time_threshold)

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
            return self.filter(self.get_app_instances_of_project_filter(user=user, project=project)).order_by(order_by)[
                :limit
            ]

        if override_default_filter:
            return self.filter(filter_func).order_by(order_by)[:limit]

        return (
            self.filter(self.get_app_instances_of_project_filter(user=user, project=project))
            .filter(filter_func)
            .order_by(order_by)[:limit]
        )

    def user_can_create(self, user, project, app_slug):
        apps_per_project = {} if project.apps_per_project is None else project.apps_per_project

        limit = apps_per_project[app_slug] if app_slug in apps_per_project else None
        app = Apps.objects.get(slug=app_slug)

        if not app.user_can_create:
            return False

        num_of_app_instances = self.filter(
            ~Q(app_status__status="Deleted"),
            app__slug=app_slug,
            project=project,
        ).count()

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
    app_status = models.OneToOneField(AppStatus, on_delete=models.RESTRICT, related_name="%(class)s", null=True)

    url = models.URLField(blank=True, null=True)
    updated_on = models.DateTimeField(auto_now=True)

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
            **self.flavor.to_dict(self.app.slug) if self.flavor else {},
            storageClass=settings.STORAGECLASS,
            namespace=settings.NAMESPACE,
            release=self.subdomain.subdomain if self.subdomain else "deleted",  # This is legacy and should be changed
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
