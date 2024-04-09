from django.apps import apps
from django.conf import settings
from django.db.models import Q
from django.shortcuts import get_object_or_404, render

from portal.views import get_public_apps

from .models import Collection

PublishedModel = apps.get_model(app_label=settings.PUBLISHEDMODEL_MODEL)


def index(request):
    template = "collections/index.html"

    collection_objects = Collection.objects.all().order_by("-created_on")

    context = {"collection_objects": collection_objects}

    return render(request, template, context=context)


def collection(request, slug, id=0):
    template = "collections/collection.html"

    collection = get_object_or_404(Collection, slug=slug)
    collection_published_apps, request = get_public_apps(request, id=id, collection=slug)
    collection_published_models = PublishedModel.objects.all().filter(collections__slug=slug)

    context = {
        "collection": collection,
        "collection_published_apps": collection_published_apps,
        "collection_published_models": collection_published_models,
    }

    return render(request, template, context=context)
