from django.db.models import Q
from django.shortcuts import get_object_or_404, render

from portal.views import get_public_apps

from .models import Collection


def collection(request, slug):
    collection = get_object_or_404(Collection, slug=slug)
    published_apps, request = get_public_apps(request, id=id)
    collection_published_apps = published_apps.filter(collections__slug=slug)
    return render(
        request,
        "collections/collection.html",
        {
            "collection": collection,
            "collection_published_apps": collection_published_apps,
        },
    )
