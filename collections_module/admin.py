from django.contrib import admin

from .models import Collection


class CollectionAdmin(admin.ModelAdmin):
    readonly_fields = ["connected_apps"]

    def connected_apps(self, obj):
        apps = obj.app_instances.all()
        app_list = ", ".join([app.name for app in apps])
        return app_list or "No apps connected"


admin.site.register(Collection, CollectionAdmin)
