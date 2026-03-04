import re

import requests
from crispy_forms.layout import HTML, Div, Field, MultiField
from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.safestring import mark_safe

from apps.forms.field.common import SRVCommonDivField
from apps.helpers import validate_docker_image, validate_ghcr_image
from apps.models import VolumeInstance
from projects.models import PersistentVolumeMountPath


class ContainerImageMixin:
    """Mixin to add a reusable container image field and validation method."""

    image = forms.CharField(
        max_length=255,
        required=True,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "docker.io/username/image-name:image-tag",
                "list": "docker-image-list",
            }
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._setup_container_image_field()

    def _setup_container_image_field(self):
        """Setup the container image field in the form."""
        self.fields["image"] = self.image

    def _setup_container_image_helper(self):
        """Returns the crispy layout for the container image field."""
        return Div(
            SRVCommonDivField(
                "image",
                placeholder="docker.io/username/image-name:image-tag",
                list="docker-image-list",
            ),
            HTML('<datalist id="docker-image-list"></datalist>'),
            css_class="mb-3",
        )

    def clean_image(self):
        """Validate the container image input."""
        image = self.cleaned_data.get("image", "").strip()

        if not image:
            self.add_error("image", "Container image field cannot be empty.")
            return image

        if "ghcr.io" in image:
            try:
                validate_ghcr_image(image)
            except ValidationError as e:
                self.add_error("image", f"Error validating GHCR image: {str(e)}")
                return image

        if "docker.io" in image:
            try:
                validate_docker_image(image)
            except ValidationError as e:
                self.add_error("image", f"Error validating Docker image: {str(e)}")
                return image

        return image


class StorageMixin:
    mount_path = forms.ModelChoiceField(
        queryset=PersistentVolumeMountPath.objects.none(), required=False, empty_label="None", label="Storage"
    )

    def _set_up_mount_path_field(self):
        mount_paths_queryset = (
            PersistentVolumeMountPath.objects.filter(volume__project__pk=self.project.pk).exclude(
                volume__latest_user_action__in=["Deleting", "SystemDeleting"]
            )
            if self.project_pk
            else PersistentVolumeMountPath.objects.none()
        )

        if self.instance and self.instance.pk:
            if self.instance.volume and self.instance.path:
                mount_path, created = PersistentVolumeMountPath.objects.get_or_create(
                    volume=self.instance.volume,
                    mount_path=self.instance.path,
                )
            else:
                mount_path = None
                created = False

            self.fields["mount_path"].queryset = mount_paths_queryset

            if created and not self.instance.mount_path_id:
                self.instance.mount_path = mount_path

            if not self.is_bound:
                self.initial["mount_path"] = self.instance.mount_path_id or (mount_path.pk if mount_path else None)
        else:
            self.fields["mount_path"].queryset = mount_paths_queryset
            self.initial["mount_path"] = None
        self.fields["mount_path"].help_text = mark_safe(
            "Attach storage to your application. Specified path should already exist in your docker container.<br>"
            "Click on 'Manage Storage' to request more storage and create new mount paths."
        )

    def _set_up_mount_path_helper(self):
        return SRVCommonDivField("mount_path", template="apps/storage_field.html", project_slug=self.project.slug)

    def _clean(self):
        cleaned = super().clean()  # keep parent validations, if any
        mount_path_data: PersistentVolumeMountPath = cleaned.get("mount_path")

        if mount_path_data is not None:
            cleaned["volume"] = mount_path_data.volume
            cleaned["path"] = mount_path_data.mount_path
        else:
            # User selected "None": remove storage linkage
            cleaned["mount_path"] = None
            cleaned["volume"] = None
            cleaned["path"] = ""  # or None, depending on your model
        return cleaned


class VolumeMixin:
    volume = forms.ModelChoiceField(
        queryset=VolumeInstance.objects.none(), required=False, empty_label="None", label="Volume"
    )

    def _set_up_volume_field(self):
        volume_queryset = (
            VolumeInstance.objects.filter(project__pk=self.project_pk).exclude(
                latest_user_action__in=["Deleting", "SystemDeleting"]
            )
            if self.project_pk
            else VolumeInstance.objects.none()
        )

        self.fields["volume"].queryset = volume_queryset
        self.fields["volume"].initial = volume_queryset
        self.fields["volume"].help_text = (
            f"Select a storage volume to attach to your {self.model_name}. "
            f"You can increase your default storage allocation by clicking on 'Manage storage'."
        )

    def _set_up_volume_helper(self):
        return SRVCommonDivField("volume", template="apps/storage_field.html", project_slug=self.project.slug)


class CreatorsMixin:
    """Mixin to add creators field functionality for managing app creators."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Add hidden creators field
        self.fields["creators"] = forms.CharField(required=False, widget=forms.HiddenInput(), initial="[]")

        self._initialize_creators()

    def _initialize_creators(self):
        """Initialize the creators field with the current user."""
        import json

        if hasattr(self, "request") and self.request and self.request.user.is_authenticated:
            user = self.request.user
            creators_data = [
                {
                    "name": user.get_full_name() or user.username,
                    "email": user.email or "",
                }
            ]
            self.fields["creators"].initial = json.dumps(creators_data)

    def get_creators_display(self):
        """Get display text for current creators."""
        import json

        if hasattr(self, "request") and self.request and self.request.user.is_authenticated:
            user = self.request.user
            name = user.get_full_name() or user.username
            email = user.email or ""
            return f"{name} <{email}>" if email else name
        return "No user logged in"

    def get_creators_field_layout(self):
        """Get the complete crispy forms layout for the creators field."""
        from crispy_forms.layout import HTML, Div

        if not (hasattr(self, "request") and self.request and self.request.user.is_authenticated):
            return Div()  # Return empty div if no user

        user = self.request.user
        user_name = user.get_full_name() or user.username
        user_email = user.email or ""

        # Prepare user data as JSON for the data-creator attribute
        import json

        user_creator_data = json.dumps(
            {"name": user_name, "email": user_email, "affiliation": "", "orcid": ""}
        ).replace(
            '"', "&quot;"
        )  # Escape quotes for HTML attribute

        return Div(
            HTML(
                '<label class="form-label">Creators '
                '<span class="bi bi-question-circle text-muted ms-2" '
                'data-bs-toggle="tooltip" data-bs-placement="right" '
                'data-bs-original-title="Manage the creators and contributors for this application.">'
                "</span></label>"
            ),
            "creators",  # Hidden field
            HTML(
                '<div class="mb-2">'
                '<small class="text-muted">Drag to reorder creators</small>'
                "</div>"
                '<ul id="creatorsSortableList" class="list-group mb-3">'
                f'<li class="list-group-item d-flex justify-content-between align-items-center" style="cursor: move;" '
                f'data-creator="{user_creator_data}">'
                f"<div><strong>{user_name}</strong>"
                + (f'<br><small class="text-muted">{user_email}</small>' if user_email else "")
                + "</div>"
                '<span class="badge bg-primary">Creator</span>'
                "</li>"
                "</ul>"
                '<script src="https://code.jquery.com/ui/1.13.2/jquery-ui.min.js"></script>'
                "<script>"
                "$(document).ready(function() {"
                '$("#creatorsSortableList").sortable({ placeholder: "list-group-item bg-light", cursor: "move" });'
                "});"
                "</script>"
            ),
            HTML(
                '<div class="mt-2">'
                "<button type='button' class='btn btn-outline-secondary btn-sm' "
                "data-bs-toggle='modal' data-bs-target='#creatorsModal'>"
                '<span class="fas fa-plus text-muted"></span> Add Creator'
                "</button></div>"
            ),
            css_class="mb-3",
        )

    def get_creators_data(self):
        """Get the parsed creators data from the form."""
        import json

        # Try to get from cleaned_data first (after form validation)
        if hasattr(self, "cleaned_data") and self.cleaned_data:
            creators_json = self.cleaned_data.get("creators", "[]")
        else:
            # Fall back to raw field value (before form validation)
            creators_field = self.fields.get("creators")
            if creators_field and hasattr(creators_field, "initial"):
                creators_json = creators_field.initial or "[]"
            else:
                creators_json = "[]"

        try:
            creators_data = json.loads(creators_json) if creators_json else []
            return creators_data
        except (json.JSONDecodeError, TypeError):
            return []


class KeywordTagsValidationMixin:
    def clean_keyword_tags(self):
        """Validate the invenio_tags input against the autocomplete API."""
        print("clean_keyword_tags called")
        tags_value = self.cleaned_data.get("invenio_tags", "").strip()
        tags_list = [tag.strip() for tag in tags_value.split("|") if tag.strip()]
        if not tags_list:
            tags_list = [tag.strip() for tag in tags_value.split() if tag.strip()]

        from doi_minting.services.keywords_service import VocabularyMemoryService

        service = VocabularyMemoryService()
        valid_tags = []
        for tag in tags_list:
            found = False
            for term in service.term_metadata.values():
                if (term.subject or "").lower() == tag.lower():
                    valid_tags.append(tag)
                    found = True
                    break
            if not found:
                self.add_error("invenio_tags", f"Tag '{tag}' is not valid.")
                return []
        return valid_tags
