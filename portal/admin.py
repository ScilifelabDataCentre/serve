from django.contrib import admin

from .models import (
    Collection,
    EventsObject,
    NewsObject,
    PublicModelObject,
    PublishedModel,
)


class CollectionAdmin(admin.ModelAdmin):
    search_fields = ("name", "maintainer__username")
    list_display = ("name", "maintainer", "website")
    readonly_fields = ["connected_apps"]

    def connected_apps(self, obj):
        apps = obj.app_instances.all()
        app_list = ", ".join([app.name for app in apps])
        return app_list or "No apps connected"


class EventsAdmin(admin.ModelAdmin):
    list_display = ("title", "start_time")
    search_fields = ["title"]


class NewsAdmin(admin.ModelAdmin):
    list_display = ("title", "created_on")
    search_fields = ["title"]


admin.site.register(Collection, CollectionAdmin)
admin.site.register(NewsObject, NewsAdmin)
admin.site.register(EventsObject, EventsAdmin)
admin.site.register(PublishedModel)
admin.site.register(PublicModelObject)
