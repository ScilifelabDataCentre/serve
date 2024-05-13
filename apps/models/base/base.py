from datetime import datetime, timedelta
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import models
from django.db.models import Q

from apps.models.base.app_status import AppStatus
from apps.models.base.app_template import Apps
from apps.models.base.subdomain import Subdomain
from projects.models import Flavor, Project


class AppInstanceManager(models.Manager):
    model_type = "AppInstance"

    def get_app_instances_of_project_filter(self, user, project, include_deleted=False, deleted_time_delta=None):
        q = Q()

        if not include_deleted:
            if deleted_time_delta is None:
                q &= ~Q(app_status__status="Deleted")
            else:
                time_threshold = datetime.now() - timedelta(minutes=deleted_time_delta)
                q &= ~Q(app_status__status="Deleted") | Q(deleted_on__gte=time_threshold)

        q &= Q(owner=user) | Q(
            access__in=["project", "public", "private", "link"] if user.is_superuser else ["project", "public", "link"]
        )
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

    def get_available_app_dependencies(self, user, project, app_name):
        result = self.filter(
            ~Q(app_status__status="Deleted"),
            Q(owner=user) | Q(access__in=["project", "public"]),
            project=project,
            app__name=app_name,
        )

        if settings.STUDIO_ACCESSMODE == "ReadWriteOnce" and app_name == "Persistent Volume":
            for instance in result:
                exists = self.filter(
                    ~Q(app_status__status="Deleted"),
                    project=project,
                    app_dependencies=instance,
                ).exists()

                if exists:
                    result = result.exclude(id=instance.id)

        return result

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


class AbstractAppInstance(models.Model):
    objects = AppInstanceManager()

    app = models.ForeignKey(Apps, on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_related")
    chart = models.CharField(max_length=512, )
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
    flavor = models.ForeignKey(
        Flavor,
        on_delete=models.RESTRICT,
        related_name="%(class)s",
        null=True,
    )
    subdomain = models.OneToOneField(
        Subdomain,
        on_delete=models.CASCADE,
        related_name="%(class)s",
    )
    app_status = models.OneToOneField(AppStatus, on_delete=models.RESTRICT, related_name="%(class)s", null=True)

    url = models.URLField(blank=True, null=True)
    updated_on = models.DateTimeField(auto_now=True)

    class Meta:
        permissions = [("can_access_app", "Can access app service")]
        abstract = True

    def __str__(self):
        return f"{self.name} ({self.app_status.status})-{self.owner}-{self.app.name}-{self.project}"

    def get_k8s_values(self):
        k8s_values = dict(name=self.name,
                          appname=self.subdomain.subdomain,
                          project=dict(
                              name=self.project.name,
                              slug=self.project.slug),
                          service=dict(
                              name=self.subdomain.subdomain + "-" + self.app.slug,
                          ),
                          **self.subdomain.to_dict(),
                          **self.flavor.to_dict() if self.flavor else {},
                          storageClass=settings.STORAGECLASS,
                          namespace=settings.NAMESPACE,
                          release=self.subdomain.subdomain #This is legacy and should be changed
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
        from django.core import serializers
        return serializers.serialize("json", [self])