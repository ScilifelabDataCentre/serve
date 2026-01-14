from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DefaultUserAdmin
from django.contrib.auth.models import User
from django.template.response import TemplateResponse
from django.urls import path
from django.utils.html import format_html

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

    # Show both fields but make affiliation readonly to indicate it's legacy
    readonly_fields = ("affiliation",)

    fieldsets = (
        ("Organization Information", {"fields": ("organization", "affiliation", "department")}),
        ("Account Information", {"fields": ("is_approved", "why_account_needed", "note", "deleted_on")}),
    )


class EmailVerificationTableInline(admin.StackedInline):
    model = EmailVerificationTable
    can_delete = True
    verbose_name_plural = "EmailVerificationTable"
    fk_name = "user"


class EmailSendingTableAdmin(admin.ModelAdmin):
    list_display = ("from_email", "to_user", "subject", "status", "created_at")
    search_fields = ("to_email", "subject")
    list_filter = ("status", "to_user")
    readonly_fields = ("to_email", "status")
    change_form_template = "admin/common/emailsendingtable/change_form.html"

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("to_user")

    def get_urls(self):
        urls = super().get_urls()
        extra = [
            path(
                "preview/",
                self.admin_site.admin_view(self.preview_view),
                name="common_emailsendingtable_preview",
            ),
        ]
        return extra + urls

    def preview_view(self, request):
        """
        Renders a preview of the email (plain + HTML) without saving/sending anything.
        Expects a POST containing the admin form data.
        """
        ModelForm = self.get_form(request)
        form = ModelForm(request.POST, request.FILES)

        if not form.is_valid():
            # Render a helpful page instead of silently failing.
            return TemplateResponse(
                request,
                "admin/common/emailsendingtable/preview.html",
                {
                    "title": "Email preview (invalid form)",
                    "form_errors": form.errors,
                    "headers": None,
                    "plain_message": "",
                    "html_message": "",
                },
            )

        instance = form.save(commit=False)
        # Mirror the save-time behavior: `to_email` is derived from `to_user` via a signal.
        if instance.to_user:
            instance.to_email = instance.to_user.email
        plain_message, html_message = instance.render_email_bodies()

        return TemplateResponse(
            request,
            "admin/common/emailsendingtable/preview.html",
            {
                "title": "Email preview",
                "form_errors": None,
                "headers": {
                    "from_email": instance.from_email,
                    "to_user": instance.to_user,
                    "to_email": instance.to_email,
                    "subject": instance.subject,
                    "template": instance.template,
                },
                "plain_message": plain_message,
                "html_message": html_message or "",
            },
        )


class UserAdmin(DefaultUserAdmin):
    inlines = (UserProfileInline, EmailVerificationTableInline)
    list_display = (
        "email",
        "first_name",
        "last_name",
        "is_active",
        "is_staff",
        "get_organization",
        "get_ror_status",
        "is_legacy_data",
        "date_joined",
    )
    list_select_related = ("userprofile",)
    list_filter = ("is_active", "is_staff", "userprofile__is_approved")
    search_fields = ("email", "first_name", "last_name", "userprofile__organization__title", "userprofile__affiliation")
    actions = ["migrate_legacy_profiles"]

    def get_organization(self, instance):
        """Display organization name (works for both new and legacy data)"""
        try:
            return instance.userprofile.get_organization_name()
        except UserProfile.DoesNotExist:
            return "N/A"

    get_organization.short_description = "Organization"
    get_organization.admin_order_field = "userprofile__organization"

    def get_ror_status(self, instance):
        """Show ROR ID with colored indicator"""
        try:
            ror_id = instance.userprofile.get_ror_id()
            if ror_id:
                # Extract just the ID from the URL
                ror_display = ror_id.split("/")[-1] if "/" in ror_id else ror_id
                return format_html('<span style="color: green;">✓ {}</span>', ror_display)
            else:
                return format_html('<span style="color: orange;">No ROR</span>')
        except UserProfile.DoesNotExist:
            return "N/A"

    get_ror_status.short_description = "ROR ID"

    def is_legacy_data(self, instance):
        """Indicate if profile uses legacy affiliation data"""
        try:
            return instance.userprofile.is_legacy_affiliation()
        except UserProfile.DoesNotExist:
            return False

    is_legacy_data.boolean = True
    is_legacy_data.short_description = "Legacy Data"

    def migrate_legacy_profiles(self, request, queryset):
        """Admin action to migrate selected users' profiles to new organization format"""
        migrated = 0
        skipped = 0
        errors = 0

        for user in queryset:
            try:
                profile = user.userprofile
                if profile.is_legacy_affiliation():
                    if profile.migrate_to_organization():
                        migrated += 1
                    else:
                        skipped += 1
                else:
                    skipped += 1
            except UserProfile.DoesNotExist:
                errors += 1
            except Exception as e:
                errors += 1
                self.message_user(request, f"Error migrating {user.email}: {str(e)}", level="ERROR")

        # Build success message
        messages = []
        if migrated > 0:
            messages.append(f"{migrated} profile(s) migrated successfully")
        if skipped > 0:
            messages.append(f"{skipped} no legacy data")
        if errors > 0:
            messages.append(f"{errors} error(s) occurred")

        self.message_user(request, ". ".join(messages) + ".", level="SUCCESS" if errors == 0 else "WARNING")

    migrate_legacy_profiles.short_description = "Migrate selected users to new organization format"


admin.site.unregister(User)
admin.site.register(User, UserAdmin)
admin.site.register(MaintenanceMode)
admin.site.register(EmailSendingTable, EmailSendingTableAdmin)
