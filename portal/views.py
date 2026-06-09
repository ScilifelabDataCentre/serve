import json
import unicodedata
from pathlib import Path
from typing import Any

import markdown
import waffle  # type: ignore
from django.apps import apps
from django.conf import settings
from django.contrib import messages
from django.contrib.syndication.views import Feed
from django.core.mail import send_mail
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify
from django.views.generic import View

from apps.app_registry import APP_REGISTRY
from apps.models import Apps, BaseAppInstance, SocialMixin
from studio.utils import get_logger

from .forms import TeachingRequestForm
from .models import EventsObject, NewsObject

logger = get_logger(__name__)


Project = apps.get_model(app_label=settings.PROJECTS_MODEL)
PublishedModel = apps.get_model(app_label=settings.PUBLISHEDMODEL_MODEL)
Collection = apps.get_model(app_label="portal.Collection")


# TODO minor refactor
# 2. add type annotations


def __get_university_logo_keys() -> list[str]:
    logo_dir = Path(settings.BASE_DIR) / "static" / "images" / "logos" / "universities"
    if not logo_dir.exists():
        return []
    return sorted(path.stem for path in logo_dir.glob("*.png"))


def __get_ror_logo_key(ror_id: str | None) -> str | None:
    if not ror_id or ror_id == "no ror":
        return None
    ror_id = ror_id.strip().rstrip("/")
    if not ror_id:
        return None
    return ror_id.rsplit("/", 1)[-1]


def __normalize_text(value: str | None) -> str:
    text = (value or "").strip().lower()
    text = text.replace("å", "a").replace("ä", "a").replace("ö", "o")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(character for character in text if not unicodedata.combining(character))
    return " ".join(text.split())


def __get_universities_lookup() -> list[dict[str, Any]]:
    universities_path = Path(settings.STATICFILES_DIRS[0]) / "common" / "universities.json"
    with universities_path.open() as f:
        universities = json.load(f).get("universities", {})

    university_list = []
    for code, value in universities.items():
        if isinstance(value, dict):
            university_list.append(
                {
                    "code": code,
                    "name": value.get("name", ""),
                    "ror_id": value.get("ror_id", ""),
                    "aliases": value.get("aliases", []),
                }
            )
        else:
            university_list.append({"code": code, "name": value, "ror_id": "", "aliases": []})
    return university_list


def __get_university_lookup_by_name() -> dict[str, dict[str, Any]]:
    lookup = {}
    for university in __get_universities_lookup():
        for candidate in [university.get("name", ""), *university.get("aliases", [])]:
            normalized_candidate = __normalize_text(candidate)
            if normalized_candidate:
                lookup[normalized_candidate] = university
    return lookup


def __get_content_stats() -> dict[str, int]:
    apps = BaseAppInstance.objects.get_app_instances_not_deleted().filter(app__category__slug="serve")
    return {
        "n_apps": apps.count(),
        "n_apps_public": apps.filter(k8s_values__permission="public").count(),
    }


def get_public_apps(request, app_id=0, collection=None, order_by="updated_on", order_reverse=False):
    published_apps = []
    seen_app_ids = set()

    def get_queryset_for_model(app_orm):
        filters = ~Q(latest_user_action__in=["Deleting", "SystemDeleting"]) & Q(access="public")
        if collection:
            filters &= Q(collections__slug=collection)

        queryset = (
            app_orm.objects.filter(filters)
            .select_related("owner__userprofile", "k8s_user_app_status", "project", "app")
            .prefetch_related("tags")
        )
        return queryset

    app_orms = (app_model for app_model in APP_REGISTRY.iter_orm_models() if issubclass(app_model, SocialMixin))

    for app_orm in app_orms:
        queryset = get_queryset_for_model(app_orm)
        for app in queryset:
            if app.id not in seen_app_ids:
                published_apps.append(app)
                seen_app_ids.add(app.id)

    if all(hasattr(app, order_by) for app in published_apps):
        published_apps.sort(
            key=lambda app: (getattr(app, order_by) is None, getattr(app, order_by, "")), reverse=order_reverse
        )
    else:
        logger.error("Error: Invalid order_by field", exc_info=True)

    return published_apps


def add_additional_context_to_public_apps(published_apps):
    serialized_apps = []
    organizations: dict[str, str | None] = {}
    departments, tags = set(), set()
    universities_by_name = __get_university_lookup_by_name()

    for app in published_apps:
        affiliation = ""
        affiliation_search = ""
        affiliation_search_extra = ""
        dep_cleaned = ""
        department_search = ""
        department_search_extra = ""
        try:
            # Check if user has a userprofile before accessing it
            if not hasattr(app.owner, "userprofile") or not app.owner.userprofile:
                logger.debug(f"User {app.owner} has no userprofile, skipping affiliation processing")
                affs = []
            else:
                affs = app.owner.userprofile.get_affiliations()

            normalized_affiliations = []
            cleaned_departments = []

            for aff in affs or []:
                raw_affiliation = aff.get("title", "")
                ror_id = aff.get("ror_id", "")
                university_match = universities_by_name.get(__normalize_text(raw_affiliation))
                normalized_affiliation = raw_affiliation
                if university_match:
                    normalized_affiliation = university_match.get("name", raw_affiliation)
                    ror_id = ror_id or university_match.get("ror_id", "")

                if normalized_affiliation:
                    normalized_affiliations.append(normalized_affiliation)
                    organizations.setdefault(normalized_affiliation, ror_id)

                department = aff.get("department", "")
                if department not in [None, ""]:
                    cleaned_department = (
                        department.replace("Department of", "")
                        .replace("Division of ", "")
                        .replace("Institute of", "")
                        .replace("Institute for ", "")
                    )
                    cleaned_departments.append(cleaned_department)
                    departments.add(cleaned_department)

            if normalized_affiliations:
                affiliation = normalized_affiliations[0]
                affiliation_search = ",".join(dict.fromkeys(normalized_affiliations))
                affiliation_search_extra = ",".join(dict.fromkeys(normalized_affiliations[1:]))

            if cleaned_departments:
                dep_cleaned = cleaned_departments[0]
                department_search = ",".join(dict.fromkeys(cleaned_departments))
                department_search_extra = ",".join(dict.fromkeys(cleaned_departments[1:]))
        except Exception as e:
            logger.error(f"Error processing affiliations for app {app.id} (owner: {app.owner}): {e}", exc_info=True)

        # I am replacing the existing tags list by a list coming from the subjects_keywords field
        # but not renaming these anywhere else so that I avoid breaking anything
        tag_list = list(
            dict.fromkeys(
                item.get("subject", "")
                for item in (app.subjects_keywords or [])
                if isinstance(item, dict) and item.get("subject")
            )
        )
        tags.update(tag_list)
        k8s_values = getattr(app, "k8s_values", {})

        try:
            app.status_group = app.get_status_group()
        except Exception:
            app.latest_status = "unknown"
            app.status_group = "unknown"
        serialized_apps.append(
            {
                "id": app.id,
                "name": app.name,
                "description": app.description,
                "owner": app.owner.first_name + " " + app.owner.last_name,
                "orcid_id": getattr(app.owner, "userprofile", None)
                and getattr(app.owner.userprofile, "orcid_id", "")
                or "",
                "affiliation": affiliation,
                "affiliation_search": affiliation_search,
                "affiliation_search_extra": affiliation_search_extra,
                "department": dep_cleaned,
                "department_search": department_search,
                "department_search_extra": department_search_extra,
                "tag_list": tag_list,
                "tag_string": ",".join(tag_list),
                "image": k8s_values.get("appconfig", {}).get("image", "Not available"),
                "port": k8s_values.get("appconfig", {}).get("port", "Not available"),
                "userid": k8s_values.get("appconfig", {}).get("userid", "Not available"),
                "pvc": k8s_values.get("apps", {}).get("volumeK8s") or None,
                "logo": app.app.logo,
                "slug": app.app.slug,
                "app_type": "Shiny App" if app.app.name == "ShinyProxy App" else app.app.name,
                "project_slug": app.project.slug,
                "source_code_url": app.source_code_url,
                "status_group": app.status_group,
                "updated_on": app.updated_on,
                "url": app.url,
                "invenio_record_id": app.invenio_record_id,
            }
        )

    if organizations:
        unique_organizations = [
            {
                "name": name,
                "ror_id": ror_id,
                "logo_key": __get_ror_logo_key(ror_id),
            }
            for name, ror_id in sorted(organizations.items())
        ]
    else:
        universities = __get_universities_lookup()
        unique_organizations = [
            {
                "name": u["name"],
                "ror_id": u.get("ror_id", ""),
                "logo_key": __get_ror_logo_key(u.get("ror_id", "")),
            }
            for u in sorted(universities, key=lambda university: university.get("name", ""))
            if u.get("name")
        ]
    unique_departments = list(departments)
    unique_tags = list(tags)
    return serialized_apps, unique_organizations, unique_departments, unique_tags


# @silk_profile(name='Public apps')
def public_apps(request, app_id=0):
    try:
        published_apps = get_public_apps(request, app_id=app_id, order_by="updated_on", order_reverse=True)
        exclude_list = [
            "ShinyProxy App",
            "Tensorflow Serving",
            "PyTorch Serve",
            "Python Model Deployment",
            "MLFlow Serve",
        ]

        serve_category_apps = Apps.objects.filter(Q(category__name="Serve")).exclude(name__in=exclude_list)
        serialized_apps, unique_organizations, unique_departments, unique_tags = add_additional_context_to_public_apps(
            published_apps
        )
        university_logo_keys = __get_university_logo_keys()
        university_logos = [
            {
                "name": university.get("name", ""),
                "aliases": university.get("aliases", []),
                "logo_key": __get_ror_logo_key(university.get("ror_id", "")),
            }
            for university in __get_universities_lookup()
            if __get_ror_logo_key(university.get("ror_id", ""))
        ]
        try:
            total_count = None
            public_count = None
            stats_error = None
            stats = __get_content_stats()
            total_count = stats.get("n_apps", total_count)
            public_count = stats.get("n_apps_public", public_count)
        except (ValueError, KeyError) as e:
            stats_error = str(e)
            logger.warning("Content stats API failed: %s", e, exc_info=True)
    except Exception as e:
        print({"error": str(e)})

    template = "portal/apps.html"
    return render(request, template, locals())


class HomeView(View):
    template = "portal/home.html"

    def get(self, request, app_id=0):
        published_apps_updated_on = get_public_apps(request, app_id=app_id, order_by="updated_on", order_reverse=True)
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


def cite(request):
    template = "portal/cite.html"
    return render(request, template, locals())


def contact(request):
    template = "portal/contact.html"
    return render(request, template, locals())


def teaching(request):
    template = "portal/teaching.html"

    if request.method == "POST":
        form = TeachingRequestForm(request.POST)
        if form.is_valid():
            # Get form data
            name = form.cleaned_data["name"]
            email = form.cleaned_data["email"]
            course_title = form.cleaned_data.get("course_title", "")
            course_dates = form.cleaned_data.get("course_dates", "")
            course_description = form.cleaned_data["course_description"]

            # Prepare email content
            subject = "New teaching request - SciLifeLab Serve"
            message = f"""A new teaching request has been submitted:

Name: {name}
Email: {email}
Course/Workshop/Webinar Title: {course_title or 'Not provided'}
Date(s) and Time(s): {course_dates or 'Not provided'}

Description:
{course_description}

---
This email was sent from the SciLifeLab Serve teaching request form.
"""

            # Send email to ADMIN_EMAIL
            try:
                send_mail(
                    subject=subject,
                    message=message,
                    from_email=settings.EMAIL_FROM,
                    recipient_list=[settings.ADMIN_EMAIL],
                    fail_silently=False,
                )
                # Show success message
                messages.success(
                    request,
                    "Thank you! Your teaching request has been submitted successfully. We will get back to you soon.",
                )
                return redirect("portal:teaching")
            except Exception as e:
                logger.error(f"Error sending teaching request email: {e}", exc_info=True)
                messages.error(
                    request,
                    "There was an error submitting your request. Please try again later or contact us directly.",
                )
    else:
        form = TeachingRequestForm()

    return render(request, template, {"form": form})


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
    published_apps = get_public_apps(request, app_id=app_id, collection=slug)
    (
        collection_published_apps,
        unique_organizations,
        unique_departments,
        unique_tags,
    ) = add_additional_context_to_public_apps(published_apps)
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


class EventsFeed(Feed):
    title = "SciLifeLab Serve events"
    link = "/events/rss/"
    description = "List of events organised by the SciLifeLab Serve team."

    def items(self):
        return EventsObject.objects.all().order_by("-created_on")[:5]

    def item_title(self, item):
        return item.title

    def item_description(self, item):
        return item.description

    def item_link(self, item):
        base_url = reverse("portal:events")
        return f"{base_url}#{slugify(item.title)}"


class NewsFeed(Feed):
    title = "SciLifeLab Serve news"
    link = "/news/rss/"
    description = "News from the SciLifeLab Serve platform."

    def items(self):
        return NewsObject.objects.all().order_by("-created_on")[:5]

    def item_title(self, item):
        return item.title

    def item_description(self, item):
        return item.body

    def item_link(self, item):
        base_url = reverse("portal:news")
        return f"{base_url}#{slugify(item.title)}"
