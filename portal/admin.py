from django.contrib import admin

from .models import PublicModelObject, PublishedModel, NewsObject, Collection


class CollectionAdmin(admin.ModelAdmin):
    readonly_fields = ["connected_apps"]

    def connected_apps(self, obj):
        apps = obj.app_instances.all()
        app_list = ", ".join([app.name for app in apps])
        return app_list or "No apps connected"


admin.site.register(Collection, CollectionAdmin)
admin.site.register(NewsObject)
admin.site.register(PublishedModel)
admin.site.register(PublicModelObject)
