from django.apps import apps
from django.conf import settings
from django.db.models import Q
from django.shortcuts import get_object_or_404, render

from portal.views import get_public_apps

from .models import Collection

PublishedModel = apps.get_model(app_label=settings.PUBLISHEDMODEL_MODEL)


def collection(request, slug):
    collection = get_object_or_404(Collection, slug=slug)
    published_apps, request = get_public_apps(request)
    collection_published_apps = published_apps.filter(collections__slug=slug)
    collection_published_models = PublishedModel.objects.all().filter(collections__slug=slug)
    return render(
        request,
        "collections/collection.html",
        {
            "collection": collection,
            "collection_published_apps": collection_published_apps,
            "collection_published_models": collection_published_models,
        },
    )
