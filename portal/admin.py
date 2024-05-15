from django.contrib import admin

from .models import PublicModelObject, PublishedModel, NewsObject

admin.site.register(NewsObject)
admin.site.register(PublishedModel)
admin.site.register(PublicModelObject)
