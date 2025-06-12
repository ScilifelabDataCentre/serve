from datetime import timedelta

import markdown
import waffle  # type: ignore
from django.apps import apps
from django.conf import settings
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.generic import View

from apps.app_registry import APP_REGISTRY
from apps.models import Apps, BaseAppInstance, SocialMixin
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

    # Select published apps
    published_apps = []
    # because shiny appears twice we have to ensure uniqueness
    seen_app_ids = set()

    def get_unique_apps(queryset, app_ids_to_exclude):
        """Get from queryset app orm models, that are not present in ``seen_app_ids``"""
        unique_app_ids_ = set()
        unique_apps_ = []
        for app in queryset:
            if app.id not in app_ids_to_exclude and app.id not in unique_app_ids_:
                unique_app_ids_.add(app.id)
                unique_apps_.append(app)
        return unique_apps_, unique_app_ids_

    app_orms = (app_model for app_model in APP_REGISTRY.iter_orm_models() if issubclass(app_model, SocialMixin))

    for app_orm in app_orms:
        filters = ~Q(latest_user_action__in=["Deleting", "SystemDeleting"]) & Q(access="public")
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
            app.status_group = app.get_status_group()
        except:  # noqa E722 TODO refactor: Add exception
            app.latest_status = "unknown"
            app.status_group = "unknown"
    organizations = []
    departments = []
    tags = []
    # Extract app config for use in Django templates
    for app in published_apps:
        try:
            organizations.append(app.owner.userprofile.affiliation)
            if app.owner.userprofile.department not in [None, ""]:
                dep = app.owner.userprofile.department.replace("Department of", "").replace("Division of ", "")
                app.owner.userprofile.department = dep
                departments.append(dep)
        except Exception:
            logger.error("Error: There is no Userprofile", exc_info=True)
        tags.extend(app.tags.get_tag_list())
        if getattr(app, "k8s_values", False):
            app.image = app.k8s_values.get("appconfig", {}).get("image", "Not available")
            app.port = app.k8s_values.get("appconfig", {}).get("port", "Not available")
            app.userid = app.k8s_values.get("appconfig", {}).get("userid", "Not available")
            app.pvc = app.k8s_values.get("apps", {}).get("volumeK8s") or None
    unique_organizations = set(organizations)
    unique_departments = set(departments)
    unique_tags = set(tags)

    request.session.modified = True
    return published_apps, request, unique_organizations, unique_departments, unique_tags


def public_apps(request, app_id=0):
    published_apps, request, unique_organizations, unique_departments, unique_tags = get_public_apps(
        request, app_id=app_id, order_by="updated_on", order_reverse=True
    )
    exclude_list = ["ShinyProxy App", "Tensorflow Serving", "PyTorch Serve", "Python Model Deployment"]
    if not waffle.flag_is_active(request, "enable_depictio"):
        exclude_list.append("Depictio")
    serve_category_apps = Apps.objects.filter(Q(category__name="Serve")).exclude(name__in=exclude_list)
    # serve_category_apps.remove(["ShinyProxy App"])
    template = "portal/apps.html"
    return render(request, template, locals())


class HomeView(View):
    template = "portal/home.html"

    def get(self, request, app_id=0):
        published_apps_updated_on, request, unique_organizations, unique_depatments, unique_tags = get_public_apps(
            request, app_id=app_id, order_by="updated_on", order_reverse=True
        )
        published_apps_updated_on = published_apps_updated_on[:6]  # we display only 6 apps
        # TODO: add selection of N apps into the function so that it is optimized in the future with more apps in the db

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


def roadmap(request):
    template = "portal/roadmap.html"
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
    collection_published_apps, request, unique_organizations, unique_departments, unique_tags = get_public_apps(
        request, app_id=app_id, collection=slug
    )
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
