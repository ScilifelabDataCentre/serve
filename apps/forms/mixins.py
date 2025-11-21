import re

import requests
from crispy_forms.layout import HTML, Div, Field, MultiField
from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.safestring import mark_safe

from apps.forms.field.common import SRVCommonDivField
from apps.helpers import validate_docker_image, validate_ghcr_image
from projects.models import PersistentVolumeMountPath


class ContainerImageMixin:
    """Mixin to add a reusable container image field and validation method."""

    image = forms.CharField(
        max_length=255,
        required=True,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "e.g. docker.io/username/image-name:image-tag",
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
            Field(
                "image",
                css_class="form-control",
                placeholder="e.g. docker.io/username/image-name:image-tag",
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
