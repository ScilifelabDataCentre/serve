from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DefaultUserAdmin
from django.contrib.auth.models import User

from .models import (
    EmailSendingTable,
    EmailVerificationTable,
    MaintenanceMode,
    UserProfile,
)


class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    verbose_name_plural = "Profile"
    fk_name = "user"


class EmailVerificationTableInline(admin.StackedInline):
    model = EmailVerificationTable
    can_delete = True
    verbose_name_plural = "EmailVerificationTable"
    fk_name = "user"


class EmailSendingTableAdmin(admin.ModelAdmin):
    list_display = ("from_email", "to_email", "to_user", "subject", "message", "template", "status", "created_at")
    search_fields = ("to_email", "subject")
    list_filter = ("status", "to_user")
    readonly_fields = ("to_email",)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("to_user")


class UserAdmin(DefaultUserAdmin):
    inlines = (UserProfileInline, EmailVerificationTableInline)
    list_display = ("email", "first_name", "last_name", "is_active", "is_staff", "get_affiliation", "date_joined")
    list_select_related = ("userprofile",)

    def get_affiliation(self, instance):
        return instance.userprofile.affiliation

    get_affiliation.short_description = "Affiliation"  # type: ignore


admin.site.unregister(User)
admin.site.register(User, UserAdmin)
admin.site.register(MaintenanceMode)
admin.site.register(EmailSendingTable, EmailSendingTableAdmin)
