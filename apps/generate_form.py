from django.conf import settings
from django.db.models import Case, IntegerField, Q, Value, When

from models.models import Model
from projects.models import S3, Environment, Flavor, ReleaseName
from studio.utils import get_logger

from .models import AppInstance, Apps

logger = get_logger(__name__)

key_words = [
    "appobj",
    "model",
    "flavor",
    "environment",
    "volumes",
    "apps",
    "logs",
    "permissions",
    "default_values",
    "export-cli",
    "csrfmiddlewaretoken",
    "S3",
    "env_variables",
    "publishable",
]


def get_form_models(aset, project, appinstance=[]):
    dep_model = False
    models = []
    if "model" in aset:
        logger.info("app requires a model")
        dep_model = True
        if "object_type" in aset["model"]:
            object_type = aset["model"]["object_type"]
        else:
            object_type = "default"
        models = Model.objects.filter(project=project, object_type__slug=object_type)

        for model in models:
            if appinstance and model.appinstance_set.filter(pk=appinstance.pk).exists():
                logger.info(model)
                model.selected = "selected"
            else:
                model.selected = ""
    return dep_model, models


def get_form_apps(aset, project, myapp, user, appinstance=[]):
    dep_apps = False
    app_deps = []
    if "apps" in aset:
        dep_apps = True
        app_deps = dict()
        apps = aset["apps"]
        for app_name, option_type in apps.items():
            logger.info(">>>>>")
            logger.info(app_name)
            # .order_by('-revision').first()
            app_obj = Apps.objects.filter(name=app_name)
            logger.info(app_obj)
            logger.info(">>>>>")
            # TODO: Only get app instances that we have permission to list.

            app_instances = AppInstance.objects.get_available_app_dependencies(
                user=user, project=project, app_name=app_name
            )
            # TODO: Special case here for "environment" app.
            # Could be solved by supporting "condition":
            # '"appobj.app_slug":"true"'
            if app_name == "Environment":
                app_instances = AppInstance.objects.filter(
                    ~Q(state="Deleted"),
                    Q(owner=user) | Q(access__in=["project", "public"]),
                    project=project,
                    app__name=app_name,
                    parameters__contains={"appobj": {myapp.slug: True}},
                )

            for ain in app_instances:
                if appinstance and ain.appinstance_set.filter(pk=appinstance.pk).exists():
                    ain.selected = "selected"
                else:
                    ain.selected = ""

            if option_type == "one":
                app_deps[app_name] = {
                    "instances": app_instances,
                    "option_type": "",
                }
            else:
                app_deps[app_name] = {
                    "instances": app_instances,
                    "option_type": "multiple",
                }
    return dep_apps, app_deps


def get_disable_fields():
    try:
        result = settings.DISABLED_APP_INSTANCE_FIELDS
        return result if result is not None else []
    except Exception:
        return []


def get_form_primitives(app_settings, appinstance=[]):
    disabled_fields = get_disable_fields()

    all_keys = app_settings.keys()
    primitives = dict()

    for key in all_keys:
        if key not in key_words:
            primitives[key] = app_settings[key]
            if "meta" in primitives[key]:
                primitives[key]["meta_title"] = primitives[key]["meta"]["title"]
            else:
                primitives[key]["meta_title"] = key

            for disabled_field in disabled_fields:
                if disabled_field in primitives[key]:
                    del primitives[key][disabled_field]

            if appinstance and key in appinstance.parameters.keys():
                for _key, _ in app_settings[key].items():
                    is_meta_key = _key in ["meta", "meta_title"]
                    if not is_meta_key:
                        parameters_of_key = appinstance.parameters[key]

                        logger.info("_key: %s", _key)

                        if _key in parameters_of_key.keys():
                            primitives[key][_key]["default"] = parameters_of_key[_key]

    return primitives


def get_form_permission(aset, project, appinstance=[]):
    form_permissions = {
        "public": {"value": "false", "option": "false"},
        "project": {"value": "false", "option": "false"},
        "private": {"value": "true", "option": "true"},
    }
    dep_permissions = True
    if "permissions" in aset:
        form_permissions = aset["permissions"]
        # if not form_permissions:
        #     dep_permissions = False

        if appinstance:
            try:
                ai_vals = appinstance.parameters
                logger.info(ai_vals["permissions"])
                form_permissions["public"]["value"] = ai_vals["permissions"]["public"]
                form_permissions["project"]["value"] = ai_vals["permissions"]["project"]
                form_permissions["private"]["value"] = ai_vals["permissions"]["private"]
                logger.info(form_permissions)
            except Exception:
                logger.error("Permissions not set for app instance, using default.", exc_info=True)
    return dep_permissions, form_permissions


# TODO: refactor. Change default value to immutable
def get_form_appobj(aset, project, appinstance=[]):
    logger.info("CHECKING APP OBJ")
    dep_appobj = False
    appobjs = dict()
    if "appobj" in aset:
        logger.info("NEEDS APP OBJ")
        dep_appobj = True
        appobjs["objs"] = Apps.objects.all()
        appobjs["title"] = aset["appobj"]["title"]
        appobjs["type"] = aset["appobj"]["type"]

    logger.info(appobjs)
    return dep_appobj, appobjs


def get_form_environments(aset, project, app, appinstance=[]):
    logger.info("CHECKING ENVIRONMENT")
    dep_environment = False
    environments = dict()
    if "environment" in aset:
        dep_environment = True
        if aset["environment"]["type"] == "match":
            environments["objs"] = Environment.objects.filter(
                Q(project=project) | Q(project__isnull=True, public=True),
                app__slug=app.slug,
            ).order_by(
                Case(
                    When(name__contains="- public", then=Value(1)),
                    default=Value(0),
                    output_field=IntegerField(),
                ),
                "-name",
            )
        elif aset["environment"]["type"] == "any":
            environments["objs"] = Environment.objects.filter(
                Q(project=project) | Q(project__isnull=True, public=True)
            ).order_by(
                Case(
                    When(name__contains="- public", then=Value(1)),
                    default=Value(0),
                    output_field=IntegerField(),
                ),
                "-name",
            )
        elif "apps" in aset["environment"]:
            environments["objs"] = Environment.objects.filter(
                Q(project=project) | Q(project__isnull=True, public=True),
                app__slug__in=aset["environment"]["apps"],
            ).order_by(
                Case(
                    When(name__contains="- public", then=Value(1)),
                    default=Value(0),
                    output_field=IntegerField(),
                ),
                "-name",
            )

        environments["title"] = aset["environment"]["title"]
        if appinstance:
            ai_vals = appinstance.parameters
            environments["selected"] = ai_vals["environment"]["pk"]

    return dep_environment, environments


def get_form_S3(aset, project, app, appinstance=[]):
    logger.info("CHECKING S3")
    dep_S3 = False
    s3stores = []
    if "S3" in aset:
        dep_S3 = True
        s3stores = S3.objects.filter(project=project)
    return dep_S3, s3stores


def generate_form(aset, project, app, user, appinstance=[]):
    form = dict()
    form["dep_model"], form["models"] = get_form_models(aset, project, appinstance)
    form["dep_apps"], form["app_deps"] = get_form_apps(aset, project, app, user, appinstance)
    form["dep_appobj"], form["appobjs"] = get_form_appobj(aset, project, appinstance)
    form["dep_environment"], form["environments"] = get_form_environments(aset, project, app, appinstance)
    form["dep_S3"], form["s3stores"] = get_form_S3(aset, project, app, appinstance)

    form["dep_vols"] = False
    form["dep_flavor"] = False
    if "flavor" in aset:
        form["dep_flavor"] = True
        if appinstance and appinstance.flavor:
            form["current_flavor"] = Flavor.objects.filter(project=project, id=appinstance.flavor.id)
            form["flavors"] = Flavor.objects.filter(project=project).exclude(id=appinstance.flavor.id)
        else:
            form["current_flavor"] = None
            form["flavors"] = Flavor.objects.filter(project=project)

    form["primitives"] = get_form_primitives(aset, appinstance)
    form["dep_permissions"], form["form_permissions"] = get_form_permission(aset, project, appinstance)
    release_names = ReleaseName.objects.filter(project=project, status="active")
    form["release_names"] = release_names
    return form
