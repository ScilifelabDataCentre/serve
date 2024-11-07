from datetime import timedelta

import markdown
from django.apps import apps
from django.conf import settings
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.generic import View

from apps.app_registry import APP_REGISTRY
from apps.models import BaseAppInstance, SocialMixin
from studio.utils import get_logger

from .models import EventsObject, NewsObject

logger = get_logger(__name__)


Project = apps.get_model(app_label=settings.PROJECTS_MODEL)
PublishedModel = apps.get_model(app_label=settings.PUBLISHEDMODEL_MODEL)
Collection = apps.get_model(app_label="portal.Collection")


# TODO minor refactor
# 2. add type annotations
def get_public_apps(request, app_id=0, collection=None, order_by="updated_on", order_reverse=False):
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

    # Select published apps
    published_apps = []
    # because shiny appears twice we have to ensure uniqueness
    seen_app_ids = set()

    def get_unique_apps(queryset, app_ids_to_exclude):
        """Get from queryset app orm models, that are not present in ``seen_app_ids``"""
        unique_app_ids_ = set()
        unique_apps_ = []
        for app in queryset:
            if app.id not in app_ids_to_exclude and app_id not in unique_app_ids_:
                unique_app_ids_.add(app.id)
                unique_apps_.append(app)
        return unique_apps_, unique_app_ids_

    app_orms = (app_model for app_model in APP_REGISTRY.iter_orm_models() if issubclass(app_model, SocialMixin))

    for app_orm in app_orms:
        logger.info("Processing: %s", app_orm)
        filters = ~Q(app_status__status="Deleted") & Q(access="public")
        if collection:
            filters &= Q(collections__slug=collection)
        published_apps_qs = app_orm.objects.filter(filters)

        unique_apps, unique_app_ids = get_unique_apps(published_apps_qs, seen_app_ids)
        published_apps += unique_apps
        seen_app_ids.update(unique_app_ids)

    # Sort by the values specified in 'order_by' and 'reverse'
    if all(hasattr(app, order_by) for app in published_apps):
        published_apps.sort(
            key=lambda app: (getattr(app, order_by) is None, getattr(app, order_by, "")), reverse=order_reverse
        )
    else:
        logger.error("Error: Invalid order_by field", exc_info=True)

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
    published_apps, request = get_public_apps(request, app_id=app_id, order_by="updated_on", order_reverse=True)
    template = "portal/apps.html"
    return render(request, template, locals())


class HomeView(View):
    template = "portal/home.html"

    def get(self, request, app_id=0):
        all_published_apps_created_on, request = get_public_apps(
            request, app_id=app_id, order_by="created_on", order_reverse=True
        )
        all_published_apps_updated_on, request = get_public_apps(
            request, app_id=app_id, order_by="updated_on", order_reverse=True
        )

        # Make sure we don't have the same apps displayed in both Recently updated and Recently added fields
        published_apps_created_on = [
            app for app in all_published_apps_created_on if app.updated_on <= (app.created_on + timedelta(minutes=60))
        ][
            :3
        ]  # we display only 3 apps
        published_apps_updated_on = [
            app for app in all_published_apps_updated_on if app.updated_on > (app.created_on + timedelta(minutes=60))
        ][
            :3
        ]  # we display only 3 apps

        news_objects = NewsObject.objects.all().order_by("-created_on")
        link_all_news = False
        if news_objects.count() > 3:
            news_objects = news_objects[:3]
            link_all_news = True
        else:
            news_objects = news_objects
        for news in news_objects:
            news.body_html = markdown.markdown(news.body)

        collection_objects = Collection.objects.all().order_by("-created_on")
        link_all_collections = False
        if collection_objects.count() > 3:
            collection_objects = collection_objects[:3]
            link_all_collections = True
        else:
            collection_objects = collection_objects

        events_objects = EventsObject.objects.all().order_by("-start_time")
        link_all_events = False
        if events_objects.count() > 3:
            link_all_events = True
            events_objects = events_objects[:3]
        else:
            events_objects = events_objects
        for event in events_objects:
            event.description_html = markdown.markdown(event.description)
            event.past = True if event.start_time.date() < timezone.now().date() else False

        context = {
            "published_apps_updated_on": published_apps_updated_on,
            "published_apps_created_on": published_apps_created_on,
            "news_objects": news_objects,
            "link_all_news": link_all_news,
            "collection_objects": collection_objects,
            "link_all_collections": link_all_collections,
            "events_objects": events_objects,
            "link_all_events": link_all_events,
        }

        return render(request, self.template, context=context)


def about(request):
    template = "portal/about.html"
    return render(request, template, locals())


def teaching(request):
    template = "portal/teaching.html"
    return render(request, template, locals())


def privacy(request):
    template = "portal/privacy.html"
    return render(request, template, locals())


def get_news(request):
    news_objects = NewsObject.objects.all().order_by("-created_on")
    for news in news_objects:
        news.body_html = markdown.markdown(news.body)
    return render(request, "news/news.html", {"news_objects": news_objects})


def get_collections_index(request):
    template = "collections/index.html"

    collection_objects = Collection.objects.all().order_by("-created_on")

    context = {"collection_objects": collection_objects}

    return render(request, template, context=context)


def get_collection(request, slug, app_id=0):
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


def get_events(request):
    future_events = EventsObject.objects.filter(start_time__date__gte=timezone.now().date()).order_by("start_time")
    for event in future_events:
        event.description_html = markdown.markdown(event.description)
    past_events = EventsObject.objects.filter(start_time__date__lt=timezone.now().date()).order_by("-start_time")
    for event in past_events:
        event.description_html = markdown.markdown(event.description)
    return render(request, "events/events.html", {"future_events": future_events, "past_events": past_events})
