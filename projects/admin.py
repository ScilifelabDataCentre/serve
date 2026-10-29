from django import forms
from django.conf import settings
from django.contrib import admin

from apps.models import AppEnvironmentSecret

from .models import (
    BasicAuth,
    Environment,
    Flavor,
    PersistentVolumeMountPath,
    Project,
    ProjectLog,
    ProjectTemplate,
)

admin.site.register(ProjectTemplate)
admin.site.register(ProjectLog)
admin.site.register(BasicAuth)


class AppEnvironmentSecretApprovalForm(forms.ModelForm):
    keys = forms.CharField(
        label="Approved Secret keys",
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="Optional. List one Secret key per line for individual selection. Values are not stored.",
    )

    class Meta:
        model = AppEnvironmentSecret
        fields = ("name", "keys")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.is_bound and self.instance.pk:
            self.initial["keys"] = "\n".join(self.instance.keys)

    def clean_keys(self):
        return [key.strip() for key in self.cleaned_data["keys"].splitlines() if key.strip()]


class AppEnvironmentSecretInline(admin.TabularInline):
    model = AppEnvironmentSecret
    form = AppEnvironmentSecretApprovalForm
    extra = 0

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_add_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    inlines = [AppEnvironmentSecretInline]
    search_fields = ("name", "owner__username", "project_template__name", "status")
    list_display = ("name", "owner", "status", "updated_at", "project_template")
    list_filter = ["owner", "status", "project_template"]
    actions = ["update_app_limits"]
    readonly_fields = ["created_at"]
    autocomplete_fields = ("privileged_users",)

    @admin.action(description="Reset app limits")
    def update_app_limits(self, request, queryset):
        queryset.update(apps_per_project=settings.APPS_PER_PROJECT_LIMIT)


@admin.register(Flavor)
class FlavorAdmin(admin.ModelAdmin):
    search_fields = ("name", "project__name")
    list_display = ("name", "project", "updated_at")
    list_filter = ["project"]


@admin.register(Environment)
class EnvironmentAdmin(admin.ModelAdmin):
    search_fields = ("name", "project__name")
    list_display = ("name", "project", "updated_at")
    list_filter = ["project"]


@admin.register(PersistentVolumeMountPath)
class PVCMountPathAdmin(admin.ModelAdmin):
    search_fields = ("volume__name", "mount_path")
    list_display = ("volume__project__name", "volume__subdomain", "volume", "mount_path", "volume__size")
    list_filter = ["volume__project__name"]
