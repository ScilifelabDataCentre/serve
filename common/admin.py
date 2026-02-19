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

    fieldsets = (
        ("Affiliations", {"fields": ("affiliations",)}),
        (
            "Account Information",
            {
                "fields": ("is_approved", "why_account_needed", "note", "deleted_on"),
            },
        ),
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
        "get_affiliations_display",
        "get_ror_ids_display",
        "get_departments_display",
        "date_joined",
    )
    list_select_related = ("userprofile",)
    list_filter = ("is_active", "is_staff", "userprofile__is_approved")
    search_fields = ("email", "first_name", "last_name", "userprofile__affiliations")
    actions = ["migrate_legacy_profiles"]

    @admin.display(description="Affiliations")
    def get_affiliations_display(self, instance):
        """Show all affiliation titles separated by pipe."""
        try:
            affs = instance.userprofile.get_affiliations()
            if not affs:
                return "N/A"
            return " | ".join(aff.get("title", "Unknown") for aff in affs)
        except UserProfile.DoesNotExist:
            return "N/A"

    @admin.display(description="ROR IDs")
    def get_ror_ids_display(self, instance):
        """Show all ROR IDs with colored indicators."""
        try:
            affs = instance.userprofile.get_affiliations()
            if not affs:
                return "N/A"
            parts = []
            for aff in affs:
                ror = aff.get("ror_id", "")
                if ror and ror != "no ror":
                    ror_short = ror.split("/")[-1] if "/" in ror else ror
                    parts.append(f'<span style="color: green;">✓ {ror_short}</span>')
                else:
                    parts.append('<span style="color: orange;">No ROR</span>')
            return format_html(" | ".join(parts))
        except UserProfile.DoesNotExist:
            return "N/A"

    @admin.display(description="Departments")
    def get_departments_display(self, instance):
        """Show all departments, matching affiliation order."""
        try:
            affs = instance.userprofile.get_affiliations()
            if not affs:
                return "N/A"
            return " | ".join(aff.get("department", "—") or "—" for aff in affs)
        except UserProfile.DoesNotExist:
            return "N/A"


admin.site.unregister(User)
admin.site.register(User, UserAdmin)
admin.site.register(MaintenanceMode)
admin.site.register(EmailSendingTable, EmailSendingTableAdmin)
