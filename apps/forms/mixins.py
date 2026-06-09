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
        # Pre-normalize initial so unchanged edits don't show as changed.
        if self.instance and getattr(self.instance, "image", None):
            normalized = self._normalize_image_registry(self.instance.image)
            if normalized != self.instance.image:
                self.initial["image"] = normalized

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

    @staticmethod
    def _normalize_image_registry(image: str) -> str:
        """Prepend ``docker.io/`` when the image has no explicit registry."""
        if not image:
            return image
        parts = image.split("/")
        first = parts[0]
        has_registry = len(parts) > 1 and ("." in first or ":" in first or first == "localhost")
        if has_registry:
            return image
        return f"docker.io/{image}"

    def clean_image(self):
        """Validate the container image input."""
        image = self.cleaned_data.get("image", "").strip()

        if not image:
            self.add_error("image", "Container image field cannot be empty.")
            return image

        image = self._normalize_image_registry(image)

        # Re-check max_length: prepending "docker.io/" can push past the limit.
        max_length = self.fields["image"].max_length
        if max_length and len(image) > max_length:
            self.add_error(
                "image",
                f"Image reference is too long ({len(image)} characters); maximum is {max_length}.",
            )
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

    def clean(self):
        cleaned = super().clean()  # keep parent validations, if any
        mount_path_data: PersistentVolumeMountPath = cleaned.get("mount_path")

        # Only set 'volume' and 'path' if the user actually changed mount_path or path
        path_changed = False
        if hasattr(self, "changed_data"):
            path_changed = "mount_path" in self.changed_data or "path" in self.changed_data

        if mount_path_data is not None:
            if path_changed or cleaned.get("volume") != getattr(mount_path_data, "volume", None):
                cleaned["volume"] = mount_path_data.volume
            if path_changed or cleaned.get("path") != getattr(mount_path_data, "mount_path", None):
                cleaned["path"] = mount_path_data.mount_path
        else:
            # Only clear fields if the user actually changed mount_path or path
            if path_changed:
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

        self.fields["creators"] = forms.CharField(required=False, widget=forms.HiddenInput(), initial="[]")
        self._initialize_creators()

    def _initialize_creators(self):
        """Initialize the creators field with Invenio data or current user."""
        import json

        # Check if creators field exists before trying to initialize it
        if "creators" not in self.fields:
            return

        # Resolve app owner once so both paths below can mark isOwner
        owner = None
        if self.instance and hasattr(self.instance, "owner") and self.instance.owner:
            owner = self.instance.owner
        elif hasattr(self, "project") and self.project and self.project.owner:
            owner = self.project.owner

        owner_orcid = ""
        owner_full_name = ""
        if owner:
            try:
                owner_orcid = owner.userprofile.orcid_id or ""
            except Exception:
                pass
            owner_full_name = f"{owner.first_name or ''} {owner.last_name or ''}".strip()

        # First check if we have Invenio creators data stored by add_metadata()
        if hasattr(self, "_invenio_creators") and self._invenio_creators:
            try:
                # Convert Invenio creators format to our format
                creators_data = []
                for creator in self._invenio_creators:
                    # Handle Pydantic Creator objects
                    creator_data = creator.model_dump() if hasattr(creator, "model_dump") else creator

                    # Extract person_or_org data
                    person_org = creator_data.get("person_or_org", {})
                    given_name = person_org.get("given_name", "")
                    family_name = person_org.get("family_name", "")
                    # Invenio 'name' is often "Family, Given" or "First Last"
                    invenio_full_name = person_org.get("name", "")

                    # Extract ORCID from identifiers if present
                    orcid = ""
                    identifiers = person_org.get("identifiers", [])
                    if identifiers:
                        for identifier in identifiers:
                            if identifier.get("scheme") == "orcid":
                                orcid = identifier.get("identifier", "")
                                break

                    # Extract affiliation
                    affiliation = ""
                    affiliations = creator_data.get("affiliations", [])
                    if affiliations:
                        affiliation = affiliations[0].get("name", "")

                    # If explicit given/family names are missing, parse the invenio_full_name
                    if not given_name and not family_name and invenio_full_name:
                        p_raw = [p.strip() for p in invenio_full_name.split(",") if p.strip()]
                        if len(p_raw) > 1:
                            family_name = p_raw[0]
                            given_name = " ".join(p_raw[1:])
                        else:
                            parts = invenio_full_name.split()
                            if len(parts) > 1:
                                given_name = " ".join(parts[:-1])
                                family_name = parts[-1]
                            else:
                                given_name = parts[0] if parts else ""
                                family_name = ""

                    # Final cleanup of artifacts
                    final_given = given_name.strip().strip(",")
                    final_family = family_name.strip().strip(",")

                    is_owner = bool(
                        (owner_orcid and orcid and owner_orcid == orcid)
                        or (owner_full_name and owner_full_name == f"{final_given} {final_family}".strip())
                        or (
                            owner
                            and owner.username
                            and invenio_full_name
                            and invenio_full_name.replace("@serve.scilifelab.se", "") == owner.username
                        )
                    )
                    creator_obj = {
                        "name": final_given,
                        "lastName": final_family,
                        "orcid": orcid,
                        "affiliation": affiliation,
                    }
                    if is_owner:
                        creator_obj["isOwner"] = True
                    creators_data.append(creator_obj)

                self.fields["creators"].initial = json.dumps(creators_data, sort_keys=True)
                return

            except Exception:
                # Fall through to default user initialization
                pass

        # Default initialization with app owner (for new instances or when Invenio fails)
        if owner:
            # Get owner profile data for ROR/affiliation information
            owner_affiliation = ""
            try:
                owner_profile = owner.userprofile
                if not owner_orcid:
                    owner_orcid = owner_profile.orcid_id or ""
                owner_affiliation = owner_profile.get_organization_name() or ""
            except Exception:
                # UserProfile doesn't exist or other error - use defaults
                pass

            # Get owner's first and last name
            owner_first_name = owner.first_name or owner.username
            owner_last_name = owner.last_name or "Owner"

            creators_data = [
                {
                    "name": owner_first_name,
                    "lastName": owner_last_name,
                    "orcid": owner_orcid,
                    "affiliation": owner_affiliation,
                    "isOwner": True,
                }
            ]
            self.fields["creators"].initial = json.dumps(creators_data)

    def clean_creators(self):
        """Basic validation for creators field."""
        import json

        creators_json = self.cleaned_data.get("creators", "[]")

        try:
            creators_data = json.loads(creators_json) if creators_json else []
        except (json.JSONDecodeError, TypeError):
            raise ValidationError("Invalid creators data format.")

        if not isinstance(creators_data, list):
            raise ValidationError("Creators must be a list.")

        for i, creator in enumerate(creators_data):
            if not isinstance(creator, dict):
                raise ValidationError(f"Creator {i+1} must be an object.")
            if not creator.get("name") or not creator.get("lastName"):
                raise ValidationError(f"Creator {i+1} must have both name and lastName.")
            # Temporarily disabled strict affiliation validation to debug
            # if not creator.get("affiliation"):
            #     raise ValidationError(f"Creator {i+1} must have an affiliation.")

        return creators_json

    def get_creators_field_layout(self):
        """Get the complete crispy forms layout for the creators field."""
        from crispy_forms.layout import HTML, Div

        if not (hasattr(self, "request") and self.request and self.request.user.is_authenticated):
            return Div()  # Return empty div if no user

        return Div(
            "creators",
            HTML(
                """
                <label class="form-label">Creators
                    <span class="bi bi-question-circle text-muted ms-2"
                          data-bs-toggle="tooltip"
                          data-bs-original-title="List one or more creators of the application."></span>
                </label>

                <div class="mb-2">
                    <small class="text-muted">List the creators that should appear in the citation.
                    Drag to reorder the names.</small>
                </div>

                <ul id="creatorsSortableList" class="list-group mb-3"></ul>

                <div class="mt-2">
                    <button type="button" class="btn btn-outline-secondary btn-sm" id="addCreatorBtn">
                        <span class="fas fa-plus text-muted"></span> Add creator
                    </button>
                </div>

                <script src="https://code.jquery.com/ui/1.13.2/jquery-ui.min.js"></script>
                """
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
                    valid_tags.append(
                        {
                            "subject": term.subject,
                            "subject_scheme": term.subject_scheme,
                            "classification_code": term.classification_code,
                        }
                    )
                    found = True
                    break

            if not found:
                self.add_error("invenio_tags", f"Tag '{tag}' is not valid.")
                return []

        return valid_tags
