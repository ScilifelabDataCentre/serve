import json
import re

from django.conf import settings
from django.contrib.auth.models import AbstractUser, User
from django.db import models
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django_prose_editor.fields import ProseEditorField

from studio.utils import get_logger

logger = get_logger(__name__)

_BLOCK_BREAKS_RE = re.compile(r"</(p|div|li|tr|h[1-6]|blockquote)\s*>", re.IGNORECASE)
_BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)
_TD_TH_CLOSE_RE = re.compile(r"</(td|th)\s*>", re.IGNORECASE)
_MANY_NEWLINES_RE = re.compile(r"\n{3,}")


def _html_to_plaintext(value: str) -> str:
    """
    Convert HTML-ish content to plaintext.

    Important: `strip_tags()` alone can concatenate paragraphs without spaces (e.g. "X,Here"),
    so we first translate common block/line-break tags into newlines, then strip tags,
    normalize whitespace, and preserve paragraph breaks as blank lines (\\n\\n).
    """
    if not value:
        return ""

    s = _BR_RE.sub("\n", value)
    s = _TD_TH_CLOSE_RE.sub(" ", s)
    # Treat end-of-block elements as paragraph breaks.
    s = _BLOCK_BREAKS_RE.sub("\n\n", s)
    s = strip_tags(s).replace("\xa0", " ")

    # Normalize newlines and collapse repeated spaces within each line.
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = "\n".join(" ".join(line.split()) for line in s.split("\n"))
    s = _MANY_NEWLINES_RE.sub("\n\n", s)
    return s.strip()


class UserProfileManager(models.Manager):
    def create_user_profile(self, user: User):
        user_profile = self.create(user=user)
        return user_profile


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    affiliation = models.CharField(max_length=100, blank=True)  # Keep for now
    """
    Stores organization as {"title": "Organization Name", "ror_id":
    "https://ror.org/xxxxx" or "migrated_from_legacy"}
    """
    organization = models.JSONField(default=dict, blank=True)
    department = models.CharField(max_length=100, blank=True)
    deleted_on = models.DateTimeField(null=True, blank=True)
    why_account_needed = models.TextField(max_length=1000, blank=True)

    is_approved = models.BooleanField(default=False)
    """This field marks if the user is affiliated with the university or not"""

    note = models.TextField(max_length=1000, blank=True)

    objects = UserProfileManager()

    def __str__(self):
        return f"{self.user.email}"

    def get_organization_name(self):
        """
        Get organization name, handling both new and legacy data
        """
        if self.organization and self.organization.get("title"):
            return self.organization["title"]
        elif self.affiliation:
            # Fallback to legacy affiliation
            return self.get_affiliation_display_name()
        return "Unknown"

    def get_affiliation_display_name(self):
        """
        Convert affiliation code to display name
        Handles legacy data
        """
        if not self.affiliation:
            return "Unknown"

        # Load universities mapping
        with open(settings.STATICFILES_DIRS[0] + "/common/universities.json", "r") as f:
            universities = json.load(f).get("universities", {})

        return universities.get(self.affiliation, self.affiliation)

    def get_ror_id(self):
        """
        Get ROR ID if available
        """
        if self.organization and self.organization.get("ror_id"):
            ror = self.organization["ror_id"]
            if ror not in ["no ror", "migrated_from_legacy"]:
                return ror
        return None

    def is_legacy_affiliation(self):
        """
        Check if this profile uses legacy affiliation data
        """
        return bool(self.affiliation)  # and (
        # not self.organization or
        # self.organization.get('ror_id') == 'migrated_from_legacy'
        # )

    def migrate_to_organization(self):
        """
        Migrate legacy affiliation data to the new organization field with ROR ID lookup.
        Returns True if migration was successful, False if skipped.
        """
        # Skip if already migrated or no legacy data
        if not self.is_legacy_affiliation():
            return False

        # Load universities mapping
        try:
            with open(settings.STATICFILES_DIRS[0] + "/common/universities.json", "r") as f:
                universities = json.load(f).get("universities", {})
        except (FileNotFoundError, json.JSONDecodeError, IndexError) as e:
            logger.error(f"Failed to load universities.json: {e}")
            return False

        ror_id = "migrated_from_legacy"  # Default fallback

        # Get university name from affiliation code
        # If affiliation code is not in the mapping, use default fallback
        if self.affiliation not in universities:
            logger.warning(
                f"Affiliation code '{self.affiliation}' not found in universities mapping for {self.user.email}"
            )
            title = "Other"
        else:
            university_name = universities[self.affiliation]
            title = university_name

            # Try to fetch ROR ID from ROR API
            try:
                import requests

                response = requests.get(
                    "https://api.ror.org/organizations", params={"query": university_name}, timeout=5
                )
                response.raise_for_status()
                data = response.json()

                # Look for exact or close match
                if data.get("items"):
                    for item in data.get("items", []):
                        # Extract the organization title from names array
                        item_title = ""
                        for name in item.get("names", []):
                            if "ror_display" in name.get("types", []):
                                item_title = name.get("value", "")
                                break

                        # If no ror_display found, use the first name
                        if not item_title and item.get("names"):
                            item_title = item["names"][0].get("value", "")

                        # Check for exact match (case-insensitive)
                        if item_title.lower() == university_name.lower():
                            ror_id = item.get("id", "migrated_from_legacy")
                            logger.info(f"Found ROR ID for {university_name}: {ror_id}")
                            break
                    else:
                        # If no exact match, take the first result as best guess
                        if data.get("items"):
                            first_item = data["items"][0]
                            ror_id = first_item.get("id", "migrated_from_legacy")
                            logger.warning(f"No exact match for {university_name}, using first result: {ror_id}")

            except Exception as e:
                logger.warning(f"Failed to fetch ROR ID for {university_name}: {e}. Using fallback.")
                ror_id = "migrated_from_legacy"

        # Create organization data from affiliation
        self.organization = {
            "title": title,
            "ror_id": ror_id,
            "legacy_affiliation": self.affiliation,  # Keep original for reference
        }

        try:
            self.save()
            logger.info(f"Migrated {self.user.email}: {self.affiliation} -> {university_name} (ROR: {ror_id})")
            return True
        except Exception as e:
            logger.error(f"Failed to save migration for {self.user.email}: {e}")
            return False


class EmailVerificationTable(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    token = models.CharField(max_length=100)
    date_created = models.DateTimeField(auto_now_add=True)

    def send_verification_email(self):
        from .tasks import send_verification_email_task

        send_verification_email_task(self.user.email, self.token)


class EmailSendingTable(models.Model):
    class EmailTemplate(models.TextChoices):
        account_enabled = "admin/email/account-enabled-email.html", "Account approved/enabled"
        user_not_swedish_uni = "admin/email/user-not-from-a-swedish-uni.html", "User not from a Swedish uni"

    from_email = models.EmailField(
        choices=[
            (settings.EMAIL_FROM, settings.EMAIL_FROM),
            (settings.ADMIN_EMAIL, settings.ADMIN_EMAIL),
        ],
        default=settings.ADMIN_EMAIL,
    )
    to_user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    to_email = models.EmailField(
        help_text="This field will indicate the email to which the email was sent after you hit 'Save'."
    )
    subject = models.CharField(
        max_length=255,
        help_text="Subject of the email. "
        "If there already exists a ticket on Edge, you can use its subject"
        " to track email history through it.",
        blank=False,
        null=False,
    )
    message = ProseEditorField(
        help_text="Type your message here if you want to write it manually. Alternatively, "
        "choose one of the templates. Supports rich text formatting.",
        # Provide an explicit extensions config so django-prose-editor runs in "normal mode".
        # This is required when sanitize=True; otherwise it falls back to legacy mode where
        # sanitization expects a config and crashes.
        extensions={
            "Bold": True,
            "Italic": True,
            "BulletList": True,
            "ListItem": True,
            "OrderedList": True,
            "Link": True,
        },
        blank=True,
        default="<p>Dear X,</p><p>Kind regards,<br>SciLifeLab Serve team</p>",
        sanitize=True,
    )
    template = models.CharField(
        max_length=100,
        choices=EmailTemplate.choices,
        help_text="Select a template if you do not want to type a message "
        "manually. If selected, anything in the Message field will be ignored.",
        null=True,
        blank=True,
    )
    status = models.CharField(
        choices=[("sent", "Sent"), ("failed", "Failed")],
        help_text="This field will indicate whether the email was successfully sent after you hit 'Save'.",
        default="pending",
        max_length=10,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def render_email_bodies(self) -> tuple[str, str]:
        """
        Returns (plain_text, html) for the email that would be sent.
        """
        plain_message: str

        if self.template:
            user_firstname = self.to_user.first_name if self.to_user else ""
            html_message = render_to_string(self.template, {"user_firstname": user_firstname})
            plain_message = _html_to_plaintext(html_message)
        else:
            # When edited with django-prose-editor, `message` will usually be HTML.
            html_message = self.message
            plain_message = _html_to_plaintext(self.message)

        return plain_message, html_message

    def send_email(self):
        from common.tasks import send_email_task

        logger.info(f"Sending an email to {self.to_email} from the admin panel email sending form.")

        plain_message, html_message = self.render_email_bodies()

        send_email_task(
            subject=self.subject,
            message=plain_message,
            html_message=html_message,
            recipient_list=[self.to_email, settings.ADMIN_EMAIL],
            fail_silently=False,
            from_email=self.from_email,
        )


class FixtureVersion(models.Model):
    filename = models.CharField(max_length=255, unique=True)
    hash = models.CharField(max_length=64)  # Length of a SHA-256 hash

    def __str__(self):
        return f"{self.filename} - {self.hash}"


class MaintenanceMode(models.Model):
    login_and_signup_disabled = models.BooleanField(default=False)
    message_in_header = models.TextField(max_length=1000, blank=True)
    message_in_footer = models.TextField(max_length=1000, blank=True)
