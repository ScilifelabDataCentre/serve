import json
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import pytz
import requests
from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import (
    get_password_validators,
    validate_password,
)
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db.models import Q
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.template import loader
from django.utils.safestring import mark_safe
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import generics
from rest_framework.authentication import SessionAuthentication
from rest_framework.authtoken.models import Token
from rest_framework.authtoken.views import ObtainAuthToken
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.mixins import (
    CreateModelMixin,
    ListModelMixin,
    RetrieveModelMixin,
    UpdateModelMixin,
)
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from api.services.loki import query_unique_ip_count
from apps.constants import HandleUpdateStatusResponseCode
from apps.helpers import get_select_options, handle_update_status_request
from apps.models import AppCategories, Apps, BaseAppInstance, Subdomain
from apps.tasks import delete_resource
from apps.types_.subdomain import SubdomainCandidateName
from models.models import ObjectType
from portal.models import PublishedModel
from projects.models import Environment, Flavor, ProjectLog, ProjectTemplate
from projects.tasks import create_resources_from_template, delete_project_apps
from studio.utils import get_logger

from .APIpermissions import AdminPermission, IsTokenAuthenticated, ProjectPermission
from .serializers import (
    AppInstanceSerializer,
    AppSerializer,
    EnvironmentSerializer,
    FlavorsSerializer,
    Metadata,
    MetadataSerializer,
    MLModelSerializer,
    Model,
    ModelLog,
    ModelLogSerializer,
    ObjectTypeSerializer,
    Project,
    ProjectSerializer,
    ProjectTemplateSerializer,
    UserSerializer,
)
from .utils import fetch_docker_hub_images_and_tags

logger = get_logger(__name__)


# A customized version of the obtain_auth_token view
# It will either create or fetch the user token
# https://www.django-rest-framework.org/api-guide/authentication/#tokenauthentication
class CustomAuthToken(ObtainAuthToken):
    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]

        token, created = Token.objects.get_or_create(user=user)

        # If the existing token is older than AUTH_TOKEN_EXPIRATION, then recreate the object
        # The token.created field contains a datetime value
        token_expiry = token.created + timedelta(seconds=settings.AUTH_TOKEN_EXPIRATION)

        if not created and datetime.now(timezone.utc) > token_expiry:
            print(f"INFO - Token expired as of {token_expiry}. Now generating a new token.")
            token.delete()
            token, created = Token.objects.get_or_create(user=user)
            token_expiry = token.created + timedelta(seconds=settings.AUTH_TOKEN_EXPIRATION)

        return Response({"token": token.key, "user_id": user.pk, "email": user.email, "expires": token_expiry})


class ObjectTypeList(
    GenericViewSet,
    CreateModelMixin,
    RetrieveModelMixin,
    UpdateModelMixin,
    ListModelMixin,
):
    permission_classes = (
        IsAuthenticated,
        ProjectPermission,
    )
    serializer_class = ObjectTypeSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["id", "name", "slug"]

    def get_queryset(self):
        return ObjectType.objects.all()


class ModelList(
    GenericViewSet,
    CreateModelMixin,
    RetrieveModelMixin,
    UpdateModelMixin,
    ListModelMixin,
):
    permission_classes = (
        IsAuthenticated,
        ProjectPermission,
    )
    serializer_class = MLModelSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["id", "name", "version", "object_type"]

    def get_queryset(self):
        """
        This view should return a list of all the models
        for the currently authenticated user.
        """
        return Model.objects.filter(project__pk=self.kwargs["project_pk"])

    def destroy(self, request, *args, **kwargs):
        project = Project.objects.get(id=self.kwargs["project_pk"])
        model = self.get_object()
        if model.project == project:
            model.delete()
            return HttpResponse("ok", 200)
        else:
            return HttpResponse("User is not allowed to delete object.", 403)

    def create(self, request, *args, **kwargs):
        project = Project.objects.get(id=self.kwargs["project_pk"])
        logger.info(str(project))

        try:
            model_name = request.data["name"]
            prev_model = Model.objects.filter(name=model_name, project=project).order_by("-version")
            logger.info("Previous Model Objects: %s", prev_model)
            if len(prev_model) > 0:
                logger.info("ACCESS")
                access = prev_model[0].access
                logger.info(access)

            else:
                access = "PR"
            release_type = request.data["release_type"]
            version = request.data["version"]
            description = request.data["description"]
            model_card = request.data["model_card"]
            model_uid = request.data["uid"]
            object_type_slug = request.data["object_type"]
            object_type = ObjectType.objects.get(slug=object_type_slug)
        except Exception as err:
            logger.exception(err, exc_info=True)
            return HttpResponse("Failed to create object: incorrect input data.", 400)

        try:
            new_model = Model(
                uid=model_uid,
                name=model_name,
                description=description,
                release_type=release_type,
                version=version,
                model_card=model_card,
                project=project,
                s3=project.s3storage,
                access=access,
            )
            new_model.save()
            new_model.object_type.set([object_type])

            pmodel = PublishedModel.objects.get(name=new_model.name, project=new_model.project)
            if pmodel:
                # Model is published, so we should create a new
                # PublishModelObject.

                from models.helpers import add_pmo_to_publish

                add_pmo_to_publish(new_model, pmodel)

        except Exception as err:
            logger.exception(err, exc_info=True)
            return HttpResponse("Failed to create object: failed to save object.", 400)
        return HttpResponse("ok", 200)


class ModelLogList(
    GenericViewSet,
    CreateModelMixin,
    RetrieveModelMixin,
    UpdateModelMixin,
    ListModelMixin,
):
    permission_classes = (
        IsAuthenticated,
        ProjectPermission,
    )
    serializer_class = ModelLogSerializer
    filter_backends = [DjangoFilterBackend]
    # filterset_fields = ['id','name', 'version']

    # Not sure if this kind of function is needed for ModelLog?
    def get_queryset(self):
        return ModelLog.objects.filter(project__pk=self.kwargs["project_pk"])

    def create(self, request, *args, **kwargs):
        project = Project.objects.get(id=self.kwargs["project_pk"])

        try:
            run_id = request.data["run_id"]
            trained_model = request.data["trained_model"]
            training_started_at = request.data["training_started_at"]
            execution_time = request.data["execution_time"]
            code_version = request.data["code_version"]
            current_git_repo = request.data["current_git_repo"]
            latest_git_commit = request.data["latest_git_commit"]
            system_details = request.data["system_details"]
            cpu_details = request.data["cpu_details"]
            training_status = request.data["training_status"]
        except Exception as e:
            logger.exception(e, exc_info=True)
            return HttpResponse("Failed to create training session log.", 400)

        new_log = ModelLog(
            run_id=run_id,
            trained_model=trained_model,
            project=project.name,
            training_started_at=training_started_at,
            execution_time=execution_time,
            code_version=code_version,
            current_git_repo=current_git_repo,
            latest_git_commit=latest_git_commit,
            system_details=system_details,
            cpu_details=cpu_details,
            training_status=training_status,
        )
        new_log.save()
        return HttpResponse("ok", 200)


class MetadataList(
    GenericViewSet,
    CreateModelMixin,
    RetrieveModelMixin,
    UpdateModelMixin,
    ListModelMixin,
):
    permission_classes = (
        IsAuthenticated,
        ProjectPermission,
    )
    serializer_class = MetadataSerializer
    filter_backends = [DjangoFilterBackend]
    # filterset_fields = ['id','name', 'version']

    def create(self, request, *args, **kwargs):
        project = Project.objects.get(id=self.kwargs["project_pk"])

        try:
            run_id = request.data["run_id"]
            trained_model = request.data["trained_model"]
            model_details = request.data["model_details"]
            parameters = request.data["parameters"]
            metrics = request.data["metrics"]
        except Exception as e:
            logger.exception(e, exc_info=True)
            return HttpResponse("Failed to create metadata log.", 400)

        new_md = Metadata(
            run_id=run_id,
            trained_model=trained_model,
            project=project.name,
            model_details=model_details,
            parameters=parameters,
            metrics=metrics,
        )
        new_md.save()
        return HttpResponse("ok", 200)


class MembersList(
    generics.ListAPIView,
    GenericViewSet,
    CreateModelMixin,
    RetrieveModelMixin,
    UpdateModelMixin,
    ListModelMixin,
):
    permission_classes = (
        IsAuthenticated,
        ProjectPermission,
    )
    serializer_class = UserSerializer
    filter_backends = [DjangoFilterBackend]

    def get_queryset(self):
        """
        This view should return a list of all the members
        of the project
        """
        proj = Project.objects.filter(pk=self.kwargs["project_pk"])
        owner = proj[0].owner
        auth_users = proj[0].authorized.all()
        logger.info(owner)
        logger.info(auth_users)
        ids = set()
        ids.add(owner.pk)
        for user in auth_users:
            ids.add(user.pk)
        logger.info(ids)
        users = User.objects.filter(pk__in=ids)
        logger.info(users)
        return users

    def create(self, request, *args, **kwargs):
        project = Project.objects.get(id=self.kwargs["project_pk"])
        selected_users = request.data["selected_users"]
        for username in selected_users.split(","):
            user = User.objects.get(username=username)
            project.authorized.add(user)
        project.save()
        return HttpResponse("Successfully added members.", status=200)

    def destroy(self, request, *args, **kwargs):
        logger.info("removing user")
        project = Project.objects.get(id=self.kwargs["project_pk"])
        user_id = self.kwargs["pk"]
        logger.info(user_id)
        user = User.objects.get(pk=user_id)
        logger.info("user: %s", str(user))
        if user.username != project.owner.username:
            logger.info("username " + user.username)
            project.authorized.remove(user)
            for role in settings.PROJECT_ROLES:
                return HttpResponse("Successfully removed members.", status=200)
        else:
            return HttpResponse("Cannot remove owner of project.", status=400)
        return HttpResponse("Failed to remove user.", status=400)


class ProjectList(
    generics.ListAPIView,
    GenericViewSet,
    CreateModelMixin,
    RetrieveModelMixin,
    UpdateModelMixin,
    ListModelMixin,
):
    permission_classes = (IsAuthenticated,)
    serializer_class = ProjectSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["name", "slug"]

    def get_queryset(self):
        """
        This view should return a list of all the projects
        for the currently authenticated user.
        """
        current_user = self.request.user
        return Project.objects.filter(
            Q(owner__username=current_user) | Q(authorized__pk__exact=current_user.pk),
            ~Q(status="archived"),
        ).distinct("name")

    def destroy(self, request, *args, **kwargs):
        project = self.get_object()
        if (request.user == project.owner or request.user.is_superuser) and project.status.lower() != "deleted":
            logger.info("Delete project")
            logger.info("SCHEDULING DELETION OF ALL INSTALLED APPS")
            delete_project_apps(project.slug)

            logger.info("ARCHIVING PROJECT Object")
            objects = Model.objects.filter(project=project)
            for obj in objects:
                obj.status = "AR"
                obj.save()
            project.status = "archived"
            project.save()
        else:
            logger.info("User is not allowed to delete project (must be owner).")
            return HttpResponse(
                "User is not allowed to delete project (must be owner).",
                status=403,
            )

        return HttpResponse("ok", status=200)

    def create(self, request):
        name = request.data["name"]
        description = request.data["description"]
        project = Project.objects.create_project(
            name=name,
            owner=request.user,
            description=description,
        )
        success = True

        try:
            # Create resources from the chosen template
            template_slug = request.data["template"]
            template = ProjectTemplate.objects.get(slug=template_slug)
            project_template = ProjectTemplate.objects.get(pk=template.pk)
            create_resources_from_template.delay(request.user.username, project.slug, project_template.template)

            # Reset user token
            if "oidc_id_token_expiration" in request.session:
                request.session["oidc_id_token_expiration"] = time.time() - 100
                request.session.save()
            else:
                logger.info("No token to reset.")
        except Exception:
            logger.error("could not create project resources", exc_info=True)
            success = False

        if not success:
            project.delete()
            return HttpResponse("Failed to create project.", status=200)
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

        if success:
            project.save()
            return HttpResponse(project.slug, status=200)


class ResourceList(
    GenericViewSet,
    CreateModelMixin,
    RetrieveModelMixin,
    UpdateModelMixin,
    ListModelMixin,
):
    permission_classes = (
        IsAuthenticated,
        ProjectPermission,
    )
    serializer_class = AppInstanceSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["id", "name", "app__category"]

    def create(self, request, *args, **kwargs):
        template = request.data
        # template = {
        #     "apps": request.data
        # }
        logger.info(template)
        project = Project.objects.get(id=self.kwargs["project_pk"])
        create_resources_from_template.delay(request.user.username, project.slug, json.dumps(template))
        return HttpResponse("Submitted request to create app.", status=200)


class AppInstanceList(
    GenericViewSet,
    CreateModelMixin,
    RetrieveModelMixin,
    UpdateModelMixin,
    ListModelMixin,
):
    permission_classes = (
        IsAuthenticated,
        ProjectPermission,
    )
    serializer_class = AppInstanceSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["id", "name", "app__category"]

    def get_queryset(self):
        return BaseAppInstance.objects.filter(~Q(state="Deleted"), project__pk=self.kwargs["project_pk"])

    def create(self, request, *args, **kwargs):
        project = Project.objects.get(id=self.kwargs["project_pk"])
        app_slug = request.data["slug"]
        data = request.data
        user = request.user
        import apps.helpers as helpers

        app = Apps.objects.filter(slug=app_slug).order_by("-revision")[0]

        (
            successful,
            _,
            _,
        ) = helpers.create_app_instance(
            user=user,
            project=project,
            app=app,
            app_settings=app.settings,
            data=data,
            wait=True,
        )

        if not successful:
            logger.info("create_app_instance failed")
            return HttpResponse("App creation faild", status=400)

        return HttpResponse("App created.", status=200)

    def destroy(self, request, *args, **kwargs):
        # TODO: Revisit
        raise RuntimeError("api/AppInstanceList destroy. Is this function used?")

        appinstance = self.get_object()
        # Check that user is allowed to delete app:
        # Either user owns the app, or is a member of the project
        # (Checked by project permission above)
        # and the app is set to project level permission.
        access = False

        if appinstance.access == "public":
            access = True

        if access:
            delete_resource.delay(appinstance.pk)
        else:
            return HttpResponse("User is not allowed to delete resource.", status=403)
        return HttpResponse("Deleted app.", status=200)


class FlavorsList(
    GenericViewSet,
    CreateModelMixin,
    RetrieveModelMixin,
    UpdateModelMixin,
    ListModelMixin,
):
    permission_classes = (
        IsAuthenticated,
        ProjectPermission,
    )
    serializer_class = FlavorsSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["id", "name"]

    def get_queryset(self):
        return Flavor.objects.filter(project__pk=self.kwargs["project_pk"])

    def destroy(self, request, *args, **kwargs):
        try:
            obj = self.get_object()
        except Exception as e:
            logger.error(e, exc_info=True)
            return HttpResponse("No such object.", status=400)
        obj.delete()
        return HttpResponse("Deleted object.", status=200)


class EnvironmentList(
    GenericViewSet,
    CreateModelMixin,
    RetrieveModelMixin,
    UpdateModelMixin,
    ListModelMixin,
):
    permission_classes = (
        IsAuthenticated,
        ProjectPermission,
    )
    serializer_class = EnvironmentSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["id", "name"]

    def get_queryset(self):
        return Environment.objects.filter(project__pk=self.kwargs["project_pk"])

    def destroy(self, request, *args, **kwargs):
        try:
            obj = self.get_object()
        except Exception as e:
            logger.error(e, exc_info=True)
            return HttpResponse("No such object.", status=400)
        obj.delete()
        return HttpResponse("Deleted object.", status=200)


class AppList(
    generics.ListAPIView,
    GenericViewSet,
    CreateModelMixin,
    RetrieveModelMixin,
    UpdateModelMixin,
    ListModelMixin,
):
    permission_classes = (
        IsTokenAuthenticated,
        IsAuthenticated,
        AdminPermission,
    )
    serializer_class = AppSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["id", "name", "slug", "category"]

    def get_queryset(self):
        return Apps.objects.all()

    def create(self, request, *args, **kwargs):
        logger.info("IN CREATE")
        try:
            name = request.data["name"]
            slug = request.data["slug"]
            category = AppCategories.objects.get(slug=request.data["cat"])
            description = request.data["description"]
            settings = json.loads(request.data["settings"])
            table_field = json.loads(request.data["table_field"])
            priority = request.data["priority"]
            access = "public"
            proj_list = []
            if "access" in request.data:
                try:
                    access = request.data["access"]
                    if access != "public":
                        projs = access.split(",")
                        for proj in projs:
                            tmp = Project.objects.get(slug=proj)
                            proj_list.append(tmp)
                except Exception:
                    logger.error("Invalid access field", exc_info=True)
                    return HttpResponse("Invalid access field.", status=400)

            logger.info(request.data)
            logger.info("SETTINGS")
            logger.info(settings)
            logger.info(table_field)
        except Exception:
            logger.error(request.data, exc_info=True)
            return HttpResponse("Invalid app specification.", status=400)
        logger.info("ADD APP")
        logger.info(name)
        logger.info(slug)
        try:
            app_latest_rev = Apps.objects.filter(slug=slug).order_by("-revision")
            if app_latest_rev:
                revision = app_latest_rev[0].revision + 1
            else:
                revision = 1
            app = Apps(
                name=name,
                slug=slug,
                category=category,
                settings=settings,
                chart_archive=request.FILES["chart"],
                revision=revision,
                description=description,
                table_field=table_field,
                priority=int(priority),
                access=access,
            )
            app.save()
            app.projects.add(*proj_list)
        except Exception as err:
            logger.error(err, exc_info=True)
        return HttpResponse("Created new app.", status=200)

    def destroy(self, request, *args, **kwargs):
        try:
            obj = self.get_object()
        except Exception as e:
            logger.error(e, exc_info=True)
            return HttpResponse("No such object.", status=400)
        obj.delete()
        return HttpResponse("Deleted object.", status=200)


class ProjectTemplateList(
    generics.ListAPIView,
    GenericViewSet,
    CreateModelMixin,
    RetrieveModelMixin,
    UpdateModelMixin,
    ListModelMixin,
):
    permission_classes = (
        IsTokenAuthenticated,
        IsAuthenticated,
        AdminPermission,
    )
    serializer_class = ProjectTemplateSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["id", "name", "slug"]

    def get_queryset(self):
        return ProjectTemplate.objects.all()

    def create(self, request, *args, **kwargs):
        logger.info(request.data)
        name = "KEY_NAME_MISSING"
        try:
            settings = json.loads(request.data["settings"])
            name = settings["name"]
            slug = settings["slug"]
            description = settings["description"]
            template = settings["template"]
            image = request.FILES["image"]
        except Exception:
            logger.error(request.data, exc_info=True)
            return HttpResponse("Failed to create new template: {}".format(name), status=400)

        try:
            template_latest_rev = ProjectTemplate.objects.filter(slug=slug).order_by("-revision")
            if template_latest_rev:
                revision = template_latest_rev[0].revision + 1
            else:
                revision = 1
            template = ProjectTemplate(
                name=name,
                slug=slug,
                revision=revision,
                description=description,
                template=json.dumps(template),
                image=image,
            )
            template.save()
        except Exception as err:
            logger.error(err, exc_info=True)
        return HttpResponse("Created new template: {}.".format(name), status=200)


@api_view(["GET"])
@permission_classes(
    (
        # IsAuthenticated,
    )
)
def get_subdomain_is_valid(request: HttpRequest) -> HttpResponse:
    """
    Implementation of the API method at endpoint /api/app-subdomain/validate/
    Supports the GET verb.

    The service contract for the GET action is as follows:
    :param str subdomainText: The subdomain text to validate.
    :param str app_id: The app id to check if the subdomain is already taken by the app.
    :returns: An http status code and dict containing {"isValid": bool, "message": str}

    Example request: /api/app-subdomain/validate/?subdomainText=my-subdomain&app_id=1
    """
    subdomain_text = request.GET.get("subdomainText")
    project_id = request.GET.get("project_id")
    app_id = request.GET.get("app_id")
    if subdomain_text is None:
        return Response("Invalid input. Must pass in argument subdomainText.", 400)

    # First validate for valid name
    subdomain_candidate = SubdomainCandidateName(subdomain_text, project_id)

    try:
        subdomain_candidate.validate_subdomain()
    except ValidationError as e:
        return Response({"isValid": False, "message": e.message})

    # Only check if the subdomain is available if the name is a valid subdomain name
    msg = "The subdomain is available"

    try:
        if app_id != "None" and subdomain_text == BaseAppInstance.objects.get(pk=app_id).subdomain.subdomain:
            is_valid = True
            msg = "The subdomain is already in use by the app."
        else:
            is_valid = subdomain_candidate.is_available()
            if not is_valid:
                msg = "The subdomain is not available"
    except Exception as e:
        logger.warn(f"Unable to validate subdomain {subdomain_text}. Error={str(e)}")
        is_valid = False
        msg = "The subdomain is not available. There was an error during checking availability of the subdomain."

    return Response({"isValid": is_valid, "message": msg})


@api_view(["GET"])
@permission_classes(
    (
        # IsAuthenticated,
    )
)
def get_subdomain_is_available(request: HttpRequest) -> HttpResponse:
    """
    Implementation of the API method at endpoint /api/app-subdomain/is-available/
    Supports the GET verb.

    The service contract for the GET action is as follows:
    :param str subdomainText: The subdomain text to check for availability.
    :param str project_id: The project id to check for available subdomains in the project.
    :returns: An http status code and dict containing {"isAvailable": bool}

    Example request: /api/app-subdomain/is-available/?subdomainText=my-subdomain&project_id=1
    """
    subdomain_text = request.GET.get("subdomainText")
    project_id = request.GET.get("project_id")
    if subdomain_text is None:
        return Response("Invalid input. Must pass in argument subdomainText.", 400)

    is_available = False

    try:
        subdomain_candidate = SubdomainCandidateName(subdomain_text, project_id)
        is_available = subdomain_candidate.is_available()
    except Exception as e:
        logger.warn(f"Unable to validate subdomain {subdomain_text}. Error={str(e)}")
        is_available = False

    return Response({"isAvailable": is_available})


@api_view(["GET"])
@permission_classes(
    (
        # IsAuthenticated,
    )
)
def get_subdomain_input_html(request: HttpRequest) -> HttpResponse:
    """
    Implementation of the API method at endpoint /api/app-subdomain/subdomain-input/
    Supports the GET verb.

    The service contract for the GET action is as follows:
    :param str type: The type of element to return (select, input or newinput).
    :param str project_id: The project id to check for available subdomains in the project.
    :param str initial_subdomain: The subdomain value for the app that is already created
    (will be empty for new apps).
    :returns: An http response with the HTML element.

    Example request: /api/app-subdomain/subdomain-input/?type=select&project_id=project_id
    &initial_subdomain=initial_subdomain
    """
    project_id = request.GET.get("project_id")
    request_type = request.GET.get("type")
    initial_subdomain = request.GET.get("initial_subdomain") if request.GET.get("initial_subdomain") else ""
    # default template and context is for input box
    context = {"initial_subdomain": initial_subdomain}
    template = "apps/partials/subdomain_input.html"
    if request_type == "select":
        options_list = get_select_options(project_id, initial_subdomain)
        context["options_list"] = options_list
        template = "apps/partials/subdomain_select.html"
    rendered_template = loader.get_template(template).render(context)
    response_html = mark_safe(rendered_template)
    return HttpResponse(response_html)


@api_view(["POST"])
@permission_classes(
    (
        # IsAuthenticated,
    )
)
def validate_password_request(request: HttpRequest) -> HttpResponse:
    """
    Implementation of the API method at endpoint /api/validate_password/
    Supports the POST verb.

    The service contract for the POST action is as follows:
    :param str password: The password for validation.
    :param str email: The email of the user.
    :param str first_name: The first name of the user.
    :param str last_name: The last name of the user.
    :returns: An http status code and dict containing {"isValid": bool, "message": str,"validator_name": str}
    """
    validator_response = []
    user = User(email=request.data["email"], first_name=request.data["first_name"], last_name=request.data["last_name"])
    for validator, settings_validator in zip(
        get_password_validators(settings.AUTH_PASSWORD_VALIDATORS), settings.AUTH_PASSWORD_VALIDATORS
    ):
        try:
            validate_password(password=request.data["password"], user=user, password_validators=[validator])
            validator_response.append(
                {
                    "isValid": True,
                    "message": None,
                    "validator_name": settings_validator["NAME"].split(".")[-1],
                }
            )
        except ValidationError as e:
            validator_response.append(
                {
                    "isValid": False,
                    "message": e,
                    "validator_name": settings_validator["NAME"].split(".")[-1],
                }
            )
    return Response(validator_response)


@api_view(["GET", "POST"])
@permission_classes(
    (
        IsTokenAuthenticated,
        IsAuthenticated,
        AdminPermission,
    )
)
def update_app_status(request: HttpRequest) -> HttpResponse:
    """
    Manages the app instance status.
    Implemented as a DRF function based view.
    Supports GET and POST verbs.

    The service contract for the POST verb is as follows:
    :param release str: The release id of the app instance, stored in the AppInstance.parameters dict.
    :param new-status str: The new status code.
    :param event-ts timestamp: A JSON-formatted timestamp, e.g. 2024-01-25T16:02:50.00Z.
    :param event-msg json dict: An optional json dict containing pod-msg and/or container-msg.
    :returns: An http status code and status text.
    """

    # POST verb
    if request.method == "POST":
        logger.debug("API method update_app_status called with POST verb.")

        utc = pytz.UTC

        try:
            # Parse and validate the input

            # Required input
            release = request.data["release"]

            new_status = request.data["new-status"]

            if len(new_status) > 20:
                logger.debug(f"Status code is longer than 20 chars so shortening: {new_status}")
                new_status = new_status[:20]

            event_ts = datetime.strptime(request.data["event-ts"], "%Y-%m-%dT%H:%M:%S.%fZ")
            event_ts = utc.localize(event_ts)

            # Optional
            event_msg = request.data.get("event-msg", None)

        except KeyError as err:
            logger.error(f"API method called with invalid input. Missing required input parameter: {err}")
            return Response(f"Invalid input. Missing required input parameter: {err}", 400)

        except Exception as err:
            logger.error(f"API method called with invalid input: {err}, type: {type(err)}")
            return Response(f"Invalid input. {err}", 400)

        logger.debug(
            f"API method update_app_status input: release={release}, new_status={new_status}, \
            event_ts={event_ts}, event_msg={event_msg}"
        )

        try:
            result = handle_update_status_request(release, new_status, event_ts, event_msg)

            if result == HandleUpdateStatusResponseCode.NO_ACTION:
                return Response(
                    "OK. NO_ACTION. No action performed. Possibly the event time is older \
                    than the currently stored time.",
                    200,
                )

            elif result == HandleUpdateStatusResponseCode.CREATED_FIRST_STATUS:
                return Response("OK. CREATED_FIRST_STATUS. Created a missing AppStatus.", 200)

            elif result == HandleUpdateStatusResponseCode.UPDATED_STATUS:
                return Response(
                    "OK. UPDATED_STATUS. Updated the app status. \
                    Determined that the submitted event was newer and different status.",
                    200,
                )

            elif result == HandleUpdateStatusResponseCode.UPDATED_TIME_OF_STATUS:
                return Response(
                    "OK. UPDATED_TIME_OF_STATUS. Updated only the event time of the status. \
                    Determined that the new and old status codes are the same.",
                    200,
                )

            elif result == HandleUpdateStatusResponseCode.OBJECT_NOT_FOUND:
                return Response(
                    f"OK. OBJECT_NOT_FOUND. The specified app instance was not found {release=}",
                    404,
                )

            else:
                logger.error(f"Unknown return code from handle_update_status_request() = {result}", exc_info=True)
                return Response(f"Unknown return code from handle_update_status_request() = {result}", 500)

        except ObjectDoesNotExist:
            # This is often not a problem. It typically happens during app re-deployments.
            logger.info(f"The specified app instance was not found release={release}")
            return Response(f"The specified app instance was not found {release=}", 404)

        except Exception as err:
            logger.error(f"Unable to update the status of the specified app instance {release}. {err}, {type(err)}")
            return Response(f"Unable to update the status of the specified app instance {release=}.", 500)

    # GET verb
    logger.info("API method update_app_status called with GET verb.")
    return Response({"message": "DEBUG: GET"})


@api_view(["GET"])
@permission_classes(
    (
        # IsAuthenticated,
    )
)
def container_image_search(request):
    query = request.GET.get("query", "").strip()
    if not query:
        return JsonResponse({"error": "Query parameter is required"}, status=400)

    docker_images = fetch_docker_hub_images_and_tags(query)

    return JsonResponse({"images": docker_images})


# TODO: Consider adding and using a new permission class here for static auth tokens
@api_view(["GET"])
@permission_classes(())
def get_content_review(request: HttpRequest) -> HttpResponse:
    """
    Implementation of the API method at endpoint /api/content-review/
    Supports the GET verb.

    The service contract for the GET action is as follows:
    :param str token: A static token for access of the API resource.
    :param int from_hours: The number of hours to fetch data for. Default is 48 hours.
    :returns: An http status code and dict containing the internal content review data.

    The top-level elements nested under data include:
    - stats_date_utz
    - stats_from_hours
    - stats_success
    - stats_message
    - several elements for recent users, projects and apps
    - several elements for link-only apps, non-running apps, errors apps

    Example request: /api/content-review/?token=<token>&from_hours=168
    """

    token: str = request.GET.get("token")
    if token is None:
        return JsonResponse({"error": "Unauthorized. The token parameter is required"}, status=401)

    if not validate_static_token(token):
        return JsonResponse({"error": "Unauthorized. The token is incorrect."}, status=401)

    try:
        from_hours: int = request.GET.get("from_hours")
        if from_hours is None:
            from_hours = 48

        from_hours = int(from_hours)
        time_threshold: datetime = datetime.now(timezone.utc) - timedelta(hours=from_hours)
    except Exception:
        return JsonResponse({"error": "The input from_hours in invalid."}, status=403)

    stats: dict[str, Any] = {}

    success: bool = True
    success_msg: str | None = None

    # Set to default values
    n_default: int = -1

    n_recent_projects = n_default
    n_recent_active_users = n_default
    n_recent_inactive_users = n_default
    n_recent_apps = n_default
    n_apps_link = n_default
    n_apps_not_running = n_default
    n_apps_status_error = n_default
    n_apps_suspect_status = n_default

    # Recently registered users
    try:
        n_recent_active_users = (
            User.objects.filter(is_active=True)
            .filter(is_superuser=False)
            .filter(date_joined__gte=time_threshold)
            .count()
        )

        n_recent_inactive_users = (
            User.objects.filter(is_active=False)
            .filter(is_superuser=False)
            .filter(date_joined__gte=time_threshold)
            .count()
        )
    except Exception as e:
        success = False
        success_msg = _append_status_msg(success_msg, "Error setting number of recent users (n_recent_users).")
        logger.warning(f"Unable to get the number of recent users: {e}", exc_info=True)

    # Recently created projects
    try:
        n_recent_projects = (
            Project.objects.filter(status="active").filter(created_at__gte=time_threshold).distinct("pk").count()
        )
    except Exception as e:
        success = False
        success_msg = _append_status_msg(success_msg, "Error setting number of recent projects (n_recent_projects).")
        logger.warning(f"Unable to get the number of recent projects: {e}", exc_info=True)

    # Apps
    # We loop over the apps queryset to capture all app-related information.
    try:
        # Recently created user apps
        apps = BaseAppInstance.objects.get_app_instances_not_deleted()

        n_recent_apps = 0
        n_apps_link = 0
        apps_link = []
        n_apps_not_running = 0
        apps_not_running = []
        n_apps_status_error = 0
        apps_status_error = []
        n_apps_suspect_status = 0
        apps_suspect_status = []

        for app in apps:
            if app.app.category.slug == "serve":
                # We are only interested in category Serve
                if app.created_on > time_threshold:
                    n_recent_apps += 1

                # User apps with link only access
                if app.k8s_values is not None and "permission" in app.k8s_values:
                    if app.k8s_values["permission"] == "link":
                        n_apps_link += 1
                        apps_link.append(app.name[:6])

                # Non-running user apps
                if app.atn_app_status != "Running":
                    n_apps_not_running += 1
                    apps_not_running.append(app.name[:6])

                if app.atn_app_status.startswith("Error"):
                    n_apps_status_error += 1
                    apps_status_error.append(app.name[:6])

                # Suspect user app status
                # Defined by if latest user action is either Creating or Changing
                # but the k8s status is missing or Running and the app is older than
                # 5 minutes (to account for deployments in progress)
                if (
                    app.latest_user_action in ["Creating", "Changing"]
                    and (app.k8s_user_app_status is None or app.k8s_user_app_status.status != "Running")
                    and app.created_on < datetime.now(timezone.utc) - timedelta(minutes=5)
                ):
                    n_apps_suspect_status += 1
                    k8s_status = None if app.k8s_user_app_status is None else app.k8s_user_app_status.status
                    apps_suspect_status.append(
                        {
                            "name": app.name[:6],
                            "action": app.latest_user_action,
                            "k8s_status": k8s_status,
                            "created": app.created_on,
                        }
                    )

    except Exception as e:
        success = False
        success_msg = _append_status_msg(success_msg, f"Error setting app information. {e}")
        logger.warning(f"Unable to get the app information: {e}", exc_info=True)

    # Add the generic top-level elements
    stats["stats_date_utz"] = datetime.now(timezone.utc)
    stats["stats_from_hours"] = from_hours
    stats["stats_success"] = success
    stats["stats_message"] = success_msg

    # Add content-specific elements
    stats["n_recent_active_users"] = n_recent_active_users
    stats["n_recent_inactive_users"] = n_recent_inactive_users
    stats["n_recent_projects"] = n_recent_projects

    stats["n_recent_apps"] = n_recent_apps
    stats["n_apps_link"] = n_apps_link
    stats["apps_link"] = apps_link
    stats["n_apps_not_running"] = n_apps_not_running
    stats["apps_not_running"] = apps_not_running
    stats["n_apps_status_error"] = n_apps_status_error
    stats["apps_status_error"] = apps_status_error
    stats["n_apps_suspect_status"] = n_apps_suspect_status
    stats["apps_suspect_status"] = apps_suspect_status

    data = {"data": stats}

    return JsonResponse(data)


def validate_static_token(token: str) -> bool:
    # TODO: This token will be made dynamic in the future
    return token == "T7?fK9!pL2$vN4!"


def _append_status_msg(status_msg: str | None, new_msg: str) -> str:
    """Simple helper function to format status messages."""
    if status_msg is None:
        return new_msg
    else:
        return f"{status_msg} {new_msg}"


@api_view(["GET"])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def get_unique_ingress_ip_count(request, app_subdomain: str) -> JsonResponse:
    """
    Returns the count of unique IPs that accessed the app (by subdomain) in the last 29 days.
    Only the app owner can access this endpoint.
    """
    if not app_subdomain:
        return JsonResponse({"error": "Missing required parameter: app_subdomain"}, status=400)

    try:
        app_instance = BaseAppInstance.objects.get(subdomain__subdomain=app_subdomain)
    except BaseAppInstance.DoesNotExist as e:
        logger.error("Subdomain not found. %s", e)
        return JsonResponse({"error": f"Subdomain not found. {e}"}, status=404)

    if (request.user == app_instance.owner) or request.user.is_superuser:
        try:
            count = query_unique_ip_count(app_subdomain=app_subdomain)
            return JsonResponse({"app_subdomain": app_subdomain, "unique_ip_count": count})
        except Exception as e:
            logger.error(f"Error retrieving unique IP count: {str(e)}")
            return JsonResponse({"error": f"Error retrieving data: {str(e)}"}, status=500)
    else:
        return JsonResponse({"error": "You do not have permission to access this app's monitoring data."}, status=403)
