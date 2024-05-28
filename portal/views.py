import markdown
from django.apps import apps
from django.conf import settings
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.generic import View

from apps.models import BaseAppInstance, SocialMixin
from studio.utils import get_logger

from .models import NewsObject

logger = get_logger(__name__)


Project = apps.get_orm_model(app_label=settings.PROJECTS_MODEL)
PublishedModel = apps.get_orm_model(app_label=settings.PUBLISHEDMODEL_MODEL)
Collection = apps.get_orm_model(app_label="portal.Collection")


# TODO minor refactor
# 1. Change id to app_id as it's anti-pattern to override language reserved function names
# 2. add type annotations
def get_public_apps(request, app_id=0, get_all=True, collection=None):
    try:
        projects = Project.objects.filter(
            Q(owner=request.user) | Q(authorized=request.user), status="active"
        )  # noqa: F841 local var assigned but never used
        logger.info(len(projects))
    except Exception:
        # logger.debug("User not logged in.")
        pass
    if "project" in request.session:
        project_slug = request.session["project"]  # noqa: F841 local var assigned but never used

    media_url = settings.MEDIA_URL  # noqa: F841 local var assigned but never used

    # create session object to store info about app and their tag counts
    if "app_tags" not in request.session:
        request.session["app_tags"] = {}
    # tag_count from the get request helps set num_tags
    # which helps set the number of tags to show in the template
    if "tag_count" in request.GET:
        # add app id to app_tags object
        if "app_id_add" in request.GET:
            num_tags = int(request.GET["tag_count"])
            app_id = int(request.GET["app_id_add"])
            request.session["app_tags"][str(app_id)] = num_tags
        # remove app id from app_tags object
        if "app_id_remove" in request.GET:
            num_tags = int(request.GET["tag_count"])
            app_id = int(request.GET["app_id_remove"])
            if str(app_id) in request.session["app_tags"]:
                request.session["app_tags"].pop(str(app_id))

    # reset app_tags if Apps Tab on Sidebar pressed
    if app_id == 0:
        if "tf_add" not in request.GET and "tf_remove" not in request.GET:
            request.session["app_tags"] = {}

    published_apps = []

    if collection:
        # TODO: TIDY THIS UP!

        for subclass in SocialMixin.__subclasses__():
            print(subclass, flush=True)
            published_apps_qs = subclass.objects.filter(
                ~Q(app_status__status="Deleted"), access="public", collections__slug=collection
            ).order_by("-updated_on")
            print(published_apps_qs, flush=True)
            published_apps.extend([app for app in published_apps_qs])

    else:
        for subclass in SocialMixin.__subclasses__():
            published_apps_qs = subclass.objects.filter(~Q(app_status__status="Deleted"), access="public").order_by(
                "-updated_on"
            )
            published_apps.extend([app for app in published_apps_qs])

    if len(published_apps) >= 3 and not get_all:
        published_apps = published_apps[:3]
    else:
        published_apps = published_apps
    # Get the app instance latest status (not state)
    # Similar to GetStatusView() in apps.views
    for app in published_apps:
        try:
            app.status_group = "success" if app.app_status.status in settings.APPS_STATUS_SUCCESS else "warning"
        except:  # noqa E722 TODO refactor: Add exception
            app.latest_status = "unknown"
            app.status_group = "unknown"

    # Extract app config for use in Django templates
    for app in published_apps:
        if getattr(app, "k8s_values", False):
            app.image = app.k8s_values.get("appconfig", {}).get("image", "Not available")
            app.port = app.k8s_values.get("appconfig", {}).get("port", "Not available")
            app.userid = app.k8s_values.get("appconfig", {}).get("userid", "Not available")
            app.pvc = app.k8s_values.get("apps", {}).get("volumeK8s") or None

    # create session object to store ids for tag seacrh if it does not exist
    if "app_tag_filters" not in request.session:
        request.session["app_tag_filters"] = []
    if "tf_add" in request.GET:
        tag = request.GET["tf_add"]
        if tag not in request.session["app_tag_filters"]:
            request.session["app_tag_filters"].append(tag)
    elif "tf_remove" in request.GET:
        tag = request.GET["tf_remove"]
        if tag in request.session["app_tag_filters"]:
            request.session["app_tag_filters"].remove(tag)
    elif "tag_count" not in request.GET:
        tag = ""
        request.session["app_tag_filters"] = []

    # changed list of published model only if tag filters are present
    if request.session["app_tag_filters"]:
        tagged_published_apps = []
        for app in published_apps:
            for t in app.tags.all():
                if t in request.session["app_tag_filters"]:
                    tagged_published_apps.append(app)
                    break
        published_apps = tagged_published_apps

    request.session.modified = True
    return published_apps, request


def public_apps(request, app_id=0):
    published_apps, request = get_public_apps(request, app_id=app_id)
    template = "portal/apps.html"
    return render(request, template, locals())


class HomeView(View):
    template = "portal/home.html"

    def get(self, request, app_id=0):
        published_apps, request = get_public_apps(request, app_id=app_id, get_all=False)
        published_models = PublishedModel.objects.all()
        news_objects = NewsObject.objects.all().order_by("-created_on")
        for news in news_objects:
            news.body_html = markdown.markdown(news.body)
        link_all_news = False
        if published_models.count() >= 3:
            published_models = published_models[:3]
        else:
            published_models = published_models

        if news_objects.count() > 3:
            news_objects = news_objects[:3]
            link_all_news = True
        else:
            news_objects = news_objects

        collection_objects = Collection.objects.all().order_by("-created_on")
        link_all_collections = False

        if collection_objects.count() > 3:
            collection_objects = collection_objects[:3]
            link_all_collections = True
        else:
            collection_objects = collection_objects

        context = {
            "published_apps": published_apps,
            "published_models": published_models,
            "news_objects": news_objects,
            "link_all_news": link_all_news,
            "collection_objects": collection_objects,
            "link_all_collections": link_all_collections,
        }

        return render(request, self.template, context=context)


class HomeViewDynamic(View):
    template = "portal/home.html"

    def get(self, request):
        if request.user.is_authenticated:
            return redirect("projects/")
        else:
            return HomeView.as_view()(request, app_id=0)


def about(request):
    template = "portal/about.html"
    return render(request, template, locals())


def teaching(request):
    template = "portal/teaching.html"
    return render(request, template, locals())


def privacy(request):
    template = "portal/privacy.html"
    return render(request, template, locals())


def news(request):
    news_objects = NewsObject.objects.all().order_by("-created_on")
    for news in news_objects:
        news.body_html = markdown.markdown(news.body)
    return render(request, "news/news.html", {"news_objects": news_objects})


def index(request):
    template = "collections/index.html"

    collection_objects = Collection.objects.all().order_by("-created_on")

    context = {"collection_objects": collection_objects}

    return render(request, template, context=context)


def collection(request, slug, app_id=0):
    template = "collections/collection.html"

    collection = get_object_or_404(Collection, slug=slug)
    collection_published_apps, request = get_public_apps(request, app_id=app_id, collection=slug)
    collection_published_models = PublishedModel.objects.all().filter(collections__slug=slug)

    context = {
        "collection": collection,
        "collection_published_apps": collection_published_apps,
        "collection_published_models": collection_published_models,
    }

    return render(request, template, context=context)
