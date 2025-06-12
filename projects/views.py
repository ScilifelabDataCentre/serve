import logging

from django.apps import apps
from django.conf import settings as django_settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import FieldDoesNotExist
from django.db.models import Model, Q
from django.http import (
    HttpResponse,
    HttpResponseBadRequest,
    HttpResponseForbidden,
    HttpResponseRedirect,
    JsonResponse,
)
from django.shortcuts import render, reverse
from django.utils.decorators import method_decorator
from django.views import View
from guardian.decorators import permission_required_or_403
from guardian.shortcuts import assign_perm, get_users_with_perms, remove_perm

from apps.app_registry import APP_REGISTRY
from common.tasks import send_email_task

from .exceptions import ProjectCreationException
from .models import Environment, Flavor, Project, ProjectLog, ProjectTemplate
from .tasks import create_resources_from_template, delete_project

logger = logging.getLogger(__name__)
Apps = apps.get_model(app_label=django_settings.APPS_MODEL)
AppCategories = apps.get_model(app_label=django_settings.APPCATEGORIES_MODEL)
User = get_user_model()


class IndexView(View):
    def get(self, request):
        template = "projects/index.html"
        try:
            if request.user.is_superuser:
                projects = Project.objects.filter(status="active").distinct("pk")
            else:
                projects = Project.objects.filter(
                    Q(owner=request.user.id) | Q(authorized=request.user.id),
                    status="active",
                ).distinct("pk")
        except TypeError as err:
            projects = []
            logger.error(str(err), exc_info=True)

        request.session["next"] = "/projects/"

        user_can_create = Project.objects.user_can_create(request.user)

        context = {
            "projects": projects,
            "user_can_create": user_can_create,
        }

        return render(request, template, context)


@login_required
@permission_required_or_403("can_view_project", (Project, "slug", "project_slug"))
def settings(request, project_slug):
    try:
        projects = Project.objects.filter(Q(owner=request.user) | Q(authorized=request.user), status="active").distinct(
            "pk"
        )
    except TypeError as err:
        projects = []
        logger.error(str(err), exc_info=True)

    template = "projects/settings.html"
    if request.user.is_superuser:
        project = Project.objects.filter(
            Q(slug=project_slug),
        ).first()
    else:
        project = Project.objects.filter(
            Q(owner=request.user) | Q(authorized=request.user),
            Q(slug=project_slug),
        ).first()

    if request.user.is_superuser and project.status == "deleted":
        return HttpResponse("This project has been deleted by the user.")

    try:
        User._meta.get_field("is_user")
        platform_users = User.objects.filter(
            ~Q(pk=project.owner.pk),
            ~Q(username="AnonymousUser"),
            ~Q(username="admin"),
            is_user=True,
        )
    except FieldDoesNotExist:
        platform_users = User.objects.filter(
            ~Q(pk=project.owner.pk),
            ~Q(username="AnonymousUser"),
            ~Q(username="admin"),
        )

    environments = Environment.objects.filter(project=project)
    apps_with_environment_option = (
        Apps.objects.filter(environment__isnull=False).order_by("slug", "-revision").distinct("slug")
    )

    flavors = Flavor.objects.filter(project=project)

    return render(request, template, locals())


@method_decorator(
    permission_required_or_403("can_view_project", (Project, "slug", "project_slug")),
    name="dispatch",
)
class UpdatePatternView(View):
    def validate(self, pattern):
        if pattern is None:
            return False

        _valid_patterns = [f"pattern-{x}" for x in range(1, 31)]

        return pattern in _valid_patterns

    def post(self, request, project_slug, *args, **kwargs):
        pattern = request.POST["pattern"]

        valid = self.validate(pattern)

        if valid:
            project = Project.objects.get(slug=project_slug)

            project.pattern = pattern

            project.save()

            return HttpResponse()

        return HttpResponseBadRequest()


@login_required
@permission_required_or_403("can_view_project", (Project, "slug", "project_slug"))
def change_description(request, project_slug):
    project = Project.objects.filter(
        Q(slug=project_slug),
        Q(owner=request.user) | Q(authorized=request.user) if not request.user.is_superuser else Q(),
    ).first()

    if request.method == "POST":
        name = request.POST.get("name", "")
        description = request.POST.get("description", "")
        if description != "":
            project.description = description
        else:
            project.description = None

        if name != "":
            project.name = name

        project.save()

        log = ProjectLog(
            project=project,
            module="PR",
            headline="Project description",
            description="Changed description for project",
        )
        log.save()

    return HttpResponseRedirect(
        reverse(
            "projects:settings",
            kwargs={"project_slug": project.slug},
        )
    )


def can_model_instance_be_deleted(field_name: str, instance: Model) -> bool:
    """
    Check if a model instance can be deleted by ensuring no app in APP_REGISTRY
    references it via the specified field.

    Args:
        field_name (str): The name of the field to check in APP_REGISTRY models.
        instance (Model): The model instance to check.

    Returns:
        bool: True if the instance can be safely deleted, False otherwise.
    """
    for app_orm in APP_REGISTRY.iter_orm_models():
        if hasattr(app_orm, field_name):
            queryset = app_orm.objects.filter(**{field_name: instance})
            if queryset.exists():
                return False
    return True


@login_required
@permission_required_or_403("can_view_project", (Project, "slug", "project_slug"))
def create_environment(request, project_slug):
    project = Project.objects.get(slug=project_slug)
    if not request.user.is_superuser:
        return HttpResponseForbidden()
    else:
        if request.method == "POST":
            # TODO: check input data
            name = request.POST.get("environment_name")
            repo = request.POST.get("environment_repository")
            image = request.POST.get("environment_image")
            app_pk = request.POST.get("environment_app")
            app = Apps.objects.get(pk=app_pk)
            environment = Environment(
                name=name,
                slug=name,
                project=project,
                repository=repo,
                image=image,
                app=app,
            )
            environment.save()
    return HttpResponseRedirect(
        reverse(
            "projects:settings",
            kwargs={"project_slug": project.slug},
        )
    )


@login_required
@permission_required_or_403("can_view_project", (Project, "slug", "project_slug"))
def delete_environment(request, project_slug):
    project = Project.objects.get(slug=project_slug)
    if not request.user.is_superuser:
        return HttpResponseForbidden()
    else:
        if request.method == "POST":
            pk = request.POST.get("environment_pk")
            environment = Environment.objects.get(pk=pk, project=project)

            can_environment_be_deleted = can_model_instance_be_deleted("environment", environment)

            if can_environment_be_deleted:
                environment.delete()
            else:
                messages.error(
                    request,
                    "Environment cannot be deleted because it is currently used by at least one app \
                        (can also be a deleted app).",
                )
    return HttpResponseRedirect(
        reverse(
            "projects:settings",
            kwargs={"project_slug": project.slug},
        )
    )


@login_required
@permission_required_or_403("can_view_project", (Project, "slug", "project_slug"))
def create_flavor(request, project_slug):
    project = Project.objects.get(slug=project_slug)
    if not request.user.is_superuser:
        return HttpResponseForbidden()
    else:
        if request.method == "POST":
            # TODO: Check input
            logger.info(request.POST)
            name = request.POST.get("flavor_name")
            cpu_req = request.POST.get("cpu_req")
            mem_req = request.POST.get("mem_req")
            ephmem_req = request.POST.get("ephmem_req")
            cpu_lim = request.POST.get("cpu_lim")
            mem_lim = request.POST.get("mem_lim")
            ephmem_lim = request.POST.get("ephmem_lim")
            flavor = Flavor(
                name=name,
                project=project,
                cpu_req=cpu_req,
                mem_req=mem_req,
                cpu_lim=cpu_lim,
                mem_lim=mem_lim,
                ephmem_req=ephmem_req,
                ephmem_lim=ephmem_lim,
            )
            flavor.save()
    return HttpResponseRedirect(
        reverse(
            "projects:settings",
            kwargs={"project_slug": project.slug},
        )
    )


@login_required
@permission_required_or_403("can_view_project", (Project, "slug", "project_slug"))
def delete_flavor(request, project_slug):
    project = Project.objects.get(slug=project_slug)
    if not request.user.is_superuser:
        return HttpResponseForbidden()
    else:
        if request.method == "POST":
            project = Project.objects.get(slug=project_slug)
            pk = request.POST.get("flavor_pk")
            flavor = Flavor.objects.get(pk=pk, project=project)

            can_flavor_be_deleted = can_model_instance_be_deleted("flavor", flavor)

            if can_flavor_be_deleted:
                flavor.delete()
            else:
                messages.error(
                    request,
                    "Flavor cannot be deleted because it is currently used by at least one app \
                        (can also be a deleted app).",
                )

    return HttpResponseRedirect(
        reverse(
            "projects:settings",
            kwargs={"project_slug": project.slug},
        )
    )


@method_decorator(
    permission_required_or_403("can_view_project", (Project, "slug", "project_slug")),
    name="dispatch",
)
class ProjectStatusView(View):
    def get(self, request, project_slug):
        project = Project.objects.get(slug=project_slug)

        return JsonResponse({"status": project.status})


@method_decorator(
    permission_required_or_403("can_view_project", (Project, "slug", "project_slug")),
    name="dispatch",
)
class GrantAccessToProjectView(View):
    def post(self, request, project_slug):
        selected_username = request.POST["selected_user"].lower()
        qs = User.objects.filter(username=selected_username)

        if len(qs) == 1:
            selected_user = qs[0]
            project = Project.objects.get(slug=project_slug)

            project.authorized.add(selected_user)
            assign_perm("can_view_project", selected_user, project)

            project_uri = f"{request.get_host()}/projects/{project.slug}"
            # The backslash below is used to ignore a newline
            email_body = f"""\
Hi {selected_username},

{request.user.username} added you to the project {project.name} on SciLifeLab Serve (https://serve.scilifelab.se).
You can now view the project here: {project_uri}.
If you have any questions get in touch with us at serve@scilifelab.se

Best regards,
The SciLifeLab Serve team
"""

            try:
                # Notify user via email
                send_email_task(
                    subject="You've been added to a project on SciLifeLab Serve",
                    message=email_body,
                    recipient_list=[selected_username],
                )

            except Exception as err:
                logger.exception(f"Unable to send email to user: {str(err)}", exc_info=True)

            log = ProjectLog(
                project=project,
                module="PR",
                headline="New members",
                description="1 new members have been added to the Project",
            )

            log.save()

        return HttpResponseRedirect(f"/projects/{project_slug}/settings?template=access")


@method_decorator(
    permission_required_or_403("can_view_project", (Project, "slug", "project_slug")),
    name="dispatch",
)
class RevokeAccessToProjectView(View):
    def valid_request(self, selected_username, user, project):
        if project.owner.id != user.id and not user.is_superuser:
            return [False, None]

        qs = User.objects.filter(username=selected_username)

        if len(qs) != 1:
            return [False, None]

        selected_user = qs[0]

        if selected_user not in project.authorized.all():
            return [False, None]

        return [True, selected_user]

    def post(self, request, project_slug):
        selected_username = request.POST["selected_user"]
        project = Project.objects.get(slug=project_slug)

        valid_request, selected_user = self.valid_request(
            selected_username,
            request.user,
            project,
        )

        if not valid_request:
            return HttpResponseBadRequest()

        project.authorized.remove(selected_user)
        remove_perm("can_view_project", selected_user, project)

        log = ProjectLog(
            project=project,
            module="PR",
            headline="Removed Project members",
            description="1 of members have been removed from the Project",
        )

        log.save()

        return HttpResponseRedirect(
            reverse(
                "projects:settings",
                kwargs={"project_slug": project_slug},
            )
        )


@login_required
def project_templates(request):
    user_can_create = Project.objects.user_can_create(request.user)
    if not user_can_create:
        return HttpResponseForbidden()
    template = "projects/project_templates.html"
    templates = ProjectTemplate.objects.filter(enabled=True).order_by("slug", "-revision").distinct("slug")
    media_url = django_settings.MEDIA_URL
    return render(request, template, locals())


class CreateProjectView(View):
    template_name = "projects/project_create.html"

    def get(self, request):
        user_can_create = Project.objects.user_can_create(request.user)
        if not user_can_create:
            return HttpResponseForbidden()

        pre_selected_template = request.GET.get("template")

        arr = ProjectTemplate.objects.filter(name=pre_selected_template)

        template = arr[0] if len(arr) > 0 else None

        context = {
            "template": template,
        }

        return render(
            request=request,
            context=context,
            template_name=self.template_name,
        )

    def post(self, request, *args, **kwargs):
        user_can_create = Project.objects.user_can_create(request.user)
        if not user_can_create:
            return HttpResponseForbidden()
        success = True

        template_id = request.POST.get("template_id")
        project_template = ProjectTemplate.objects.get(pk=template_id)

        name = request.POST.get("name", "default")[:200]
        description = request.POST.get("description", "")

        # Ensure no duplicate project name for the common user

        project_name_already_exists = (
            Project.objects.filter(
                owner=request.user,
                name=name,
            )
            .exclude(status="deleted")
            .exists()
        )

        if project_name_already_exists and not request.user.is_superuser:
            pre_selected_template = request.GET.get("template")
            template = ProjectTemplate.objects.filter(name=pre_selected_template).first()
            context = {"template": template}
            logger.error("A project with name '" + name + "' already exists.")

            messages.error(
                request,
                "Project cannot be created because a project with name '" + name + "' already exists.",
            )

            return render(request, self.template_name, context)

        # Try to create database project object.
        try:
            project = Project.objects.create_project(
                name=name,
                owner=request.user,
                description=description,
                status="created",
                project_template=project_template,
            )
        except ProjectCreationException:
            logger.error("Failed to create project database object.")
            success = False

        try:
            # Create resources from the chosen template

            create_resources_from_template.delay(request.user.username, project.slug, project_template.template)

        except ProjectCreationException:
            logger.error("Could not create project resources")
            success = False

        if not success:
            project.delete()
        else:
            l1 = ProjectLog(
                project=project,
                module="PR",
                headline="Project created",
                description="Created project {}".format(project.name),
            )
            l1.save()

            l2 = ProjectLog(
                project=project,
                module="PR",
                headline="Getting started",
                description="Getting started with project {}".format(project.name),
            )
            l2.save()

        next_page = request.POST.get("next", "/projects/{}".format(project.slug))

        return HttpResponseRedirect(next_page, {"message": "Created project"})


@method_decorator(
    permission_required_or_403("can_view_project", (Project, "slug", "project_slug")),
    name="dispatch",
)
class DetailsView(View):
    template_name = "projects/overview.html"

    def get(self, request, project_slug):
        project = Project.objects.get(slug=project_slug)

        if request.user.is_superuser and project.status == "deleted":
            return HttpResponse("This project has been deleted by the user.")

        resources = []
        app_ids = []
        if request.user.is_superuser:
            categories = AppCategories.objects.all().order_by("-priority")
        else:
            categories = AppCategories.objects.all().exclude(slug__in=["admin-apps"]).order_by("-priority")

        for category in categories:
            # Get all subclasses of Base

            instances_per_category_list = []
            for orm_model in APP_REGISTRY.iter_orm_models():
                # Filter instances of each subclass by project, user and status.
                # See the get_app_instances_of_project_filter method in base.py

                queryset_per_category = orm_model.objects.get_app_instances_of_project(
                    user=request.user, project=project, filter_func=Q(app__category__slug=category.slug)
                )

                if queryset_per_category:
                    # SS-1071 Added check for app_ids and instances_per_category
                    # to avoid duplicates (e.g in case of shinyapps)
                    app_ids += [obj.id for obj in queryset_per_category if obj.id not in app_ids]
                    instances_per_category_list.extend(
                        [instance for instance in queryset_per_category if instance not in instances_per_category_list]
                    )

            # Filter the available apps specified in the project template
            available_apps = [app.pk for app in project.project_template.available_apps.all()]

            apps_per_category = (
                Apps.objects.filter(category=category, user_can_create=True, pk__in=available_apps)
                .order_by("slug", "-revision")
                .distinct("slug")
            )

            resources.append(
                {
                    "title": category.name,
                    "instances": instances_per_category_list,
                    "apps": apps_per_category,
                    "timezone": "Europe/Stockholm Timezone",
                }
            )

        context = {"resources": resources, "project": project, "app_ids": app_ids, "user": request.user}

        return render(
            request=request,
            context=context,
            template_name=self.template_name,
        )


@login_required
@permission_required_or_403("can_view_project", (Project, "slug", "project_slug"))
def delete(request, project_slug):
    next_page = request.GET.get("next", "/projects/")

    if not request.user.is_superuser:
        users = User.objects.filter(username=request.user)

        if len(users) != 1:
            return HttpResponseBadRequest()

        owner = users[0]

        projects = Project.objects.filter(owner=owner, slug=project_slug)

        if len(projects) != 1:
            return HttpResponseForbidden()

        project = projects[0]
    else:
        project = Project.objects.filter(slug=project_slug).first()

    logger.info("SCHEDULING DELETION OF ALL INSTALLED APPS")
    # remove permissions to see this project
    users_with_permission = get_users_with_perms(project)
    for user in users_with_permission:
        remove_perm("can_view_project", user, project)
    # set the status to 'deleted'
    project.status = "deleted"
    project.save()
    delete_project.delay(project.pk)

    return HttpResponseRedirect(next_page, {"message": "Deleted project successfully."})
