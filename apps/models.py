import subprocess
import uuid
import yaml
from datetime import datetime, timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import models
from django.db.models import Q
from django.db.models.signals import post_save
from django.dispatch import receiver
from guardian.shortcuts import assign_perm, remove_perm
from tagulous.models import TagField
from studio.utils import get_logger



logger = get_logger(__name__)

class AppCategories(models.Model):
    name = models.CharField(max_length=512)
    priority = models.IntegerField(default=100)
    slug = models.CharField(max_length=512, default="", primary_key=True)

    def __str__(self):
        return str(self.name)


class Apps(models.Model):
    user_can_create = models.BooleanField(default=True)
    user_can_edit = models.BooleanField(default=True)
    user_can_delete = models.BooleanField(default=True)
    access = models.CharField(max_length=20, blank=True, null=True, default="public")
    category = models.ForeignKey(
        "AppCategories",
        related_name="apps",
        on_delete=models.CASCADE,
        null=True,
    )
    chart = models.CharField(max_length=512)
    chart_archive = models.FileField(upload_to="apps/", null=True, blank=True)
    created_on = models.DateTimeField(auto_now_add=True)
    description = models.TextField(blank=True, null=True, default="")
    logo = models.CharField(max_length=512, null=True, blank=True)
    name = models.CharField(max_length=512)
    priority = models.IntegerField(default=100)
    projects = models.ManyToManyField("projects.Project", blank=True)
    revision = models.IntegerField(default=1)
    settings = models.JSONField(blank=True, null=True)
    slug = models.CharField(max_length=512, blank=True, null=True)
    table_field = models.JSONField(blank=True, null=True)
    updated_on = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = (
            "slug",
            "revision",
        )

    def __str__(self):
        return str(self.name) + "({})".format(self.revision)

    def to_dict(self):
        pass


class AppInstanceManager(models.Manager):
    def get_app_instances_of_project_filter(self, user, project, include_deleted=False, deleted_time_delta=None):
        q = Q()

        if not include_deleted:
            if deleted_time_delta is None:
                q &= ~Q(state="Deleted")
            else:
                time_threshold = datetime.now() - timedelta(minutes=deleted_time_delta)
                q &= ~Q(state="Deleted") | Q(deleted_on__gte=time_threshold)

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
            ~Q(state="Deleted"),
            Q(owner=user) | Q(access__in=["project", "public"]),
            project=project,
            app__name=app_name,
        )

        if settings.STUDIO_ACCESSMODE == "ReadWriteOnce" and app_name == "Persistent Volume":
            for instance in result:
                exists = self.filter(
                    ~Q(state="Deleted"),
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
            ~Q(state="Deleted"),
            app__slug=app_slug,
            project=project,
        ).count()

        has_perm = user.has_perm("apps.add_appinstance")

        return limit is None or limit > num_of_app_instances or has_perm


class AppInstance(models.Model):
    objects = AppInstanceManager()

    access = models.CharField(max_length=20, default="private", null=True, blank=True)
    app = models.ForeignKey("Apps", on_delete=models.CASCADE, related_name="appinstance")
    app_dependencies = models.ManyToManyField("apps.AppInstance", blank=True)
    created_on = models.DateTimeField(auto_now_add=True)
    deleted_on = models.DateTimeField(null=True, blank=True)
    description = models.TextField(blank=True, null=True, default="")
    info = models.JSONField(blank=True, null=True)
    model_dependencies = models.ManyToManyField("models.Model", blank=True)
    name = models.CharField(max_length=512, default="app_name")
    owner = models.ForeignKey(
        get_user_model(),
        on_delete=models.CASCADE,
        related_name="app_owner",
        null=True,
    )
    parameters = models.JSONField(blank=True, null=True)
    project = models.ForeignKey(
        "projects.Project",
        on_delete=models.CASCADE,
        related_name="appinstance",
    )
    flavor = models.ForeignKey(
        "projects.Flavor",
        on_delete=models.RESTRICT,
        related_name="appinstance",
        null=True,
    )
    state = models.CharField(max_length=50, null=True, blank=True)
    table_field = models.JSONField(blank=True, null=True)
    tags = TagField(blank=True)
    updated_on = models.DateTimeField(auto_now=True)
    note_on_linkonly_privacy = models.TextField(blank=True, null=True, default="")
    collections = models.ManyToManyField("collections_module.Collection", blank=True, related_name="app_instances")
    source_code_url = models.URLField(blank=True, null=True)

    class Meta:
        permissions = [("can_access_app", "Can access app service")]

    def __str__(self):
        return str(self.name) + " ({})-{}-{}-{}".format(self.state, self.owner, self.app.name, self.project)


@receiver(
    post_save,
    sender=AppInstance,
    dispatch_uid="app_instance_update_permission",
)
def update_permission(sender, instance, created, **kwargs):
    owner = instance.owner

    if instance.access == "private":
        if created or not owner.has_perm("can_access_app", instance):
            assign_perm("can_access_app", owner, instance)

    else:
        if owner.has_perm("can_access_app", instance):
            remove_perm("can_access_app", owner, instance)


class AppStatus(models.Model):
    appinstance = models.ForeignKey("AppInstance", on_delete=models.CASCADE, related_name="status")
    info = models.JSONField(blank=True, null=True)
    status_type = models.CharField(max_length=15, default="app_name")
    time = models.DateTimeField(auto_now_add=True)

    class Meta:
        get_latest_by = "time"

    def __str__(self):
        return str(self.appinstance.name) + "({})".format(self.time)


class AppStatusNew(models.Model):
    info = models.JSONField(blank=True, null=True)
    status = models.CharField(max_length=15, default="Unknown")
    time = models.DateTimeField(auto_now_add=True)

    class Meta:
        get_latest_by = "time"

    def __str__(self):
        return str(self.status) + " ({})".format(self.time)


class ResourceData(models.Model):
    appinstance = models.ForeignKey("AppInstance", on_delete=models.CASCADE, related_name="resourcedata")
    cpu = models.IntegerField()
    gpu = models.IntegerField()
    mem = models.IntegerField()
    time = models.IntegerField()





##################################
from projects.models import Project, Flavor


class Social(models.Model):
    tags = TagField(blank=True)
    note_on_linkonly_privacy = models.TextField(blank=True, null=True, default="")
    #collections = models.ManyToManyField("collections_module.Collection", blank=True, related_name="app_instances")
    source_code_url = models.URLField(blank=True, null=True)
    description = models.TextField(blank=True, null=True, default="")
    
    class Meta:
        abstract = True



class Subdomain(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    subdomain = models.CharField(max_length=512, unique=True)
    project = models.ForeignKey(settings.PROJECTS_MODEL, on_delete=models.CASCADE, null=True)

    def __str__(self):
        return str(self.subdomain) + " ({})".format(self.project.name)
    
    def to_dict(self):
        return {
            "subdomain": self.subdomain,
        }



class AppInstanceManagerNew(models.Manager):
    
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
    objects = AppInstanceManagerNew()
    
    app = models.ForeignKey(Apps, on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_related")
    chart = models.CharField(max_length=512, )
    created_on = models.DateTimeField(auto_now_add=True)
    deleted_on = models.DateTimeField(null=True, blank=True)
    info = models.JSONField(blank=True, null=True)
    #model_dependencies = models.ManyToManyField("models.Model", blank=True)
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
    app_status = models.OneToOneField(AppStatusNew, on_delete=models.RESTRICT, related_name="%(class)s", null=True)

    table_field = models.JSONField(blank=True, null=True)
    updated_on = models.DateTimeField(auto_now=True)

    class Meta:
        permissions = [("can_access_app", "Can access app service")]
        abstract = True

    def __str__(self):
        return str(self.name) + " ({})-{}-{}-{}".format(self.app_status.status, self.owner, self.app.name, self.project)
    
    def set_k8s_values(self):
        
        k8s_values = dict(name = self.name,
                          appname = self.subdomain.subdomain,
                          project = dict(
                              name = self.project.name,
                              slug = self.project.slug),
                          service = dict(
                            name = self.subdomain.subdomain + "-" + self.app.slug,
                          ),
                          **self.subdomain.to_dict(),
                          **self.flavor.to_dict(),
                          storageClass = settings.STORAGECLASS,
                          namespace = settings.NAMESPACE
        )
        
        # Add global values
        k8s_values["global"] = dict(
            domain = settings.DOMAIN,
            auth_domain = settings.AUTH_DOMAIN,
            protocol = settings.AUTH_PROTOCOL,
        )
        

        self.k8s_values = k8s_values
        


class JupyterInstanceManager(AppInstanceManagerNew):
    model_type = "jupyterinstance"

class JupyterInstance(AbstractAppInstance, Social):
    objects = JupyterInstanceManager()
    ACCESS_TYPES = (
        ("project", "Project"),
        ("private", "Private"),
    )
    volume = models.ManyToManyField("VolumeInstance", blank=True)
    access = models.CharField(max_length=20, default="private", choices=ACCESS_TYPES)

    def set_k8s_values(self):
        super().set_k8s_values()
        
        self.k8s_values["permission"] = self.access,
        
        # Not the nicest perhaps, but it works since the charts assume that the volumes are on this form
        # {apps: 
        #   {volumeK8s: 
        #       {project-vol: 
        #           {release: r1582t9h9 

        volumeK8s_dict = {"volumeK8s": {}}
        for object in self.volume.all():
            volumeK8s_dict["volumeK8s"][object.name] = dict(
                release = object.subdomain.subdomain
            )
        self.k8s_values["apps"] = volumeK8s_dict
        self.save(update_fields=["k8s_values"])
        


class VolumeInstanceManager(AppInstanceManagerNew):
    model_type = "volumeinstance"

class VolumeInstance(AbstractAppInstance):
    objects = VolumeInstanceManager()
    
    def __str__(self):
        return str(self.name)
    