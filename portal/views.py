import markdown
from django.apps import apps
from django.conf import settings
from django.db.models import Q
from django.shortcuts import redirect, render
from django.views.generic import View

AppInstance = apps.get_model(app_label=settings.APPINSTANCE_MODEL)
Project = apps.get_model(app_label=settings.PROJECTS_MODEL)
PublishedModel = apps.get_model(app_label=settings.PUBLISHEDMODEL_MODEL)
NewsObject = apps.get_model(app_label="news.NewsObject")


# TODO minor refactor
# 1. Change id to app_id as it's anti-pattern to override language reserved function names
# 2. add type annotations
def get_public_apps(request, id=0, get_all=True):
    try:
        projects = Project.objects.filter(
            Q(owner=request.user) | Q(authorized=request.user), status="active"
        )  # noqa: F841 local var assigned but never used
        print(len(projects))
    except Exception:
        print("User not logged in.")
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
            id = int(request.GET["app_id_add"])
            request.session["app_tags"][str(id)] = num_tags
        # remove app id from app_tags object
        if "app_id_remove" in request.GET:
            num_tags = int(request.GET["tag_count"])
            id = int(request.GET["app_id_remove"])
            if str(id) in request.session["app_tags"]:
                request.session["app_tags"].pop(str(id))

    # reset app_tags if Apps Tab on Sidebar pressed
    if id == 0:
        if "tf_add" not in request.GET and "tf_remove" not in request.GET:
            request.session["app_tags"] = {}

    published_apps = AppInstance.objects.filter(~Q(state="Deleted"), access="public").order_by("-updated_on")
    if published_apps.count() >= 3 and not get_all:
        published_apps = published_apps[:3]
    else:
        published_apps = published_apps
    # Get the app instance latest status (not state)
    # Similar to GetStatusView() in apps.views
    for app in published_apps:
        try:
            app.latest_status = app.status.latest().status_type

            app.status_group = "success" if app.latest_status in settings.APPS_STATUS_SUCCESS else "warning"
        except:  # noqa E722 TODO refactor: Add exception
            app.latest_status = "unknown"
            app.status_group = "unknown"

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


def public_apps(request, id=0):
    published_apps, request = get_public_apps(request, id=id)
    template = "portal/apps.html"
    return render(request, template, locals())


class HomeView(View):
    template = "portal/home.html"

    def get(self, request, id=0):
        published_apps, request = get_public_apps(request, id=id, get_all=False)
        published_models = PublishedModel.objects.all()
        news_objects = NewsObject.objects.all().order_by("-created_on")
        for news in news_objects:
            news.body_html = markdown.markdown(news.body)
        link_all_news = False
        if published_models.count() >= 3:
            published_models = published_models[:3]
        else:
            published_models = published_models

        if news_objects.count() >= 3:
            news_objects = news_objects[:3]
            link_all_news = True
        else:
            news_objects = news_objects

        return render(request, self.template, locals())


class HomeViewDynamic(View):
    template = "portal/home.html"

    def get(self, request):
        if request.user.is_authenticated:
            return redirect("projects/")
        else:
            return HomeView.as_view()(request, id=0)


def about(request):
    template = "portal/about.html"
    return render(request, template, locals())


def teaching(request):
    template = "portal/teaching.html"
    return render(request, template, locals())


def privacy(request):
    template = "portal/privacy.html"
    return render(request, template, locals())
