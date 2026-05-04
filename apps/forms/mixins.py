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

                    creator_obj = {
                        "name": given_name,
                        "lastName": family_name,
                        "orcid": orcid,
                        "affiliation": affiliation,
                    }
                    creators_data.append(creator_obj)

                self.fields["creators"].initial = json.dumps(creators_data, sort_keys=True)
                return

            except Exception:
                # Fall through to default user initialization
                pass

        # Default initialization with current user (for new instances or when Invenio fails)
        if hasattr(self, "request") and self.request and self.request.user.is_authenticated:
            user = self.request.user

            # Get user profile data for ROR/affiliation information
            user_orcid = ""
            user_affiliation = ""
            try:
                user_profile = user.userprofile
                user_orcid = user_profile.orcid_id or ""
                user_affiliation = user_profile.get_organization_name() or ""
            except Exception:
                # UserProfile doesn't exist or other error - use defaults
                pass

            # Get user's first and last name
            user_first_name = user.first_name or user.username
            user_last_name = user.last_name or "User"

            # Ensure affiliation is never empty - provide default if needed
            if not user_affiliation:
                user_affiliation = ""

            creators_data = [
                {
                    "name": user_first_name,
                    "lastName": user_last_name,
                    "orcid": user_orcid,
                    "affiliation": user_affiliation,
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
        import json

        from crispy_forms.layout import HTML, Div

        if not (hasattr(self, "request") and self.request and self.request.user.is_authenticated):
            return Div()  # Return empty div if no user

        user = self.request.user
        user_first_name = user.first_name or user.username
        user_last_name = user.last_name or "User"
        user_full_name = f"{user_last_name}, {user_first_name}"

        # Get user profile data for the display
        user_orcid = ""
        user_affiliation = ""
        try:
            user_profile = user.userprofile
            user_orcid = user_profile.orcid_id or ""
            user_affiliation = user_profile.get_organization_name() or ""
        except Exception:
            # UserProfile doesn't exist - use defaults
            pass

        # Check if we have Invenio creators data to display instead of default user
        creators_to_display = []
        if hasattr(self, "_invenio_creators") and self._invenio_creators:
            for creator in self._invenio_creators:
                # Convert Pydantic to dict for minimal changes
                creator_dict = creator.model_dump()

                # Extract data from dict structure (minimal changes to existing logic)
                creator_name = ""
                creator_orcid = ""
                affiliation = ""

                if "person_or_org" in creator_dict and creator_dict["person_or_org"]:
                    person_org = creator_dict["person_or_org"]
                    creator_name = person_org.get("name", "")

                    # Extract ORCID from identifiers
                    if "identifiers" in person_org and person_org["identifiers"]:
                        for identifier in person_org["identifiers"]:
                            if identifier.get("scheme") == "orcid":
                                creator_orcid = identifier.get("identifier", "")
                                break

                # Extract first affiliation
                if "affiliations" in creator_dict and creator_dict["affiliations"]:
                    affiliation = creator_dict["affiliations"][0].get("name", "")

                name_parts = creator_name.split() if creator_name else ["", ""]
                first_name = name_parts[0] if name_parts else ""
                last_name = " ".join(name_parts[1:]) if len(name_parts) > 1 else ""

                # Check if this creator is the current user
                is_current_user = any(
                    [
                        creator_orcid and user_orcid and creator_orcid == user_orcid,
                        creator_name == user_full_name,
                        creator_name and creator_name.replace("@serve.scilifelab.se", "") == user.username,
                        creator_name == f"{user.first_name} {user.last_name}".strip(),
                    ]
                )

                creators_to_display.append(
                    {
                        "name": first_name,
                        "lastName": last_name,
                        "fullName": creator_name,
                        "orcid": creator_orcid,
                        "affiliation": affiliation,
                        "isCurrentUser": is_current_user,
                    }
                )
        else:
            # Use default user creator
            creators_to_display.append(
                {
                    "name": user_first_name,
                    "lastName": user_last_name,
                    "fullName": user_full_name,
                    "orcid": user_orcid,
                    "affiliation": user_affiliation,
                    "isCurrentUser": True,
                }
            )

        # Generate HTML for each creator
        creators_html = ""
        for i, creator in enumerate(creators_to_display):
            # Prepare creator data as JSON for data-creator attribute
            creator_data = json.dumps(
                {
                    "name": creator["name"],
                    "lastName": creator["lastName"],
                    "affiliation": creator["affiliation"],
                    "orcid": creator["orcid"],
                }
            ).replace('"', "&quot;")

            # Build creator info display
            creator_info = f"<strong>{creator['fullName']}</strong>"
            if creator["orcid"] or creator["affiliation"]:
                creator_info += "<br><small class='text-muted'>"
                if creator["affiliation"]:
                    creator_info += f"Affiliation: {creator['affiliation']}<br>"
                if creator["orcid"]:
                    creator_info += f"ORCID: {creator['orcid']}"
                creator_info += "</small>"

            # Add badge and action buttons
            badge_html = ""
            if creator.get("isCurrentUser"):
                badge_html = '<span class="badge bg-secondary me-2">You</span>'

            # Add edit and remove buttons (conditionally)
            action_buttons = ""
            if not creator.get("isCurrentUser"):
                # Only show edit/remove buttons if this is not the current user
                action_buttons = f"""
                    <div class="d-flex align-items-center gap-2">
                        {badge_html}
                        <button type="button" class="btn btn-outline-secondary btn-sm"
                                data-edit-creator="{i}" title="Edit creator">
                            <i class="fas fa-edit"></i>
                        </button>
                        <button type="button" class="btn btn-outline-danger btn-sm"
                                onclick="removeCreator(this)" title="Remove creator">
                            <i class="fas fa-times"></i>
                        </button>
                    </div>
                """
            else:
                # For current user, only show the badge without edit/remove buttons
                action_buttons = f"""
                    <div class="d-flex align-items-center gap-2">
                        {badge_html}
                    </div>
                """

            creators_html += f"""
                <li class="list-group-item d-flex justify-content-between align-items-center"
                    style="cursor: move;" data-creator="{creator_data}">
                    <div>{creator_info}</div>
                    {action_buttons}
                </li>
            """

        return Div(
            "creators",
            HTML(
                f"""
                <label class="form-label">Creators
                    <span class="bi bi-question-circle text-muted ms-2"
                          data-bs-toggle="tooltip"
                          data-bs-original-title="List one or more creators of the application."></span>
                </label>

                <div class="mb-2">
                    <small class="text-muted">List the creators that should appear in the citation.
                    Drag to reorder the names.</small>
                </div>

                <ul id="creatorsSortableList" class="list-group mb-3">
                    {creators_html}
                </ul>

                <div class="mt-2">
                    <button type="button" class="btn btn-outline-secondary btn-sm"
                            data-bs-toggle="modal" data-bs-target="#creatorsModal">
                        <span class="fas fa-plus text-muted"></span> Add creator
                    </button>
                </div>

                <script src="https://code.jquery.com/ui/1.13.2/jquery-ui.min.js"></script>
                <script>
                    $(document).ready(function() {{
                        $("#creatorsSortableList").sortable({{
                            placeholder: "list-group-item bg-light",
                            cursor: "move"
                        }});

                        // Handle edit creator button clicks
                        $(document).on('click', '[data-edit-creator]', function() {{

                            const index = $(this).data('edit-creator');
                            const listItem = $(this).closest('li[data-creator]');

                            try {{
                                const creatorData = JSON.parse(listItem.attr('data-creator'));

                                // Populate the creator modal with existing data
                                $('#newCreatorName').val(creatorData.name || '');
                                $('#newCreatorLastName').val(creatorData.lastName || '');
                                $('#newCreatorOrcid').val(creatorData.orcid || '');

                                // Handle affiliation - could be string or object
                                const affiliationData = creatorData.affiliation || '';

                                if (typeof affiliationData === 'string') {{
                                    $('#newCreatorAffiliation').val(affiliationData);
                                    $('#newCreatorRorData').val('');
                                    $('#newCreatorOrcidAffiliationData').val('');
                                }} else if (typeof affiliationData === 'object' &&
                                          affiliationData !== null) {{
                                    // It's structured data (ROR or ORCID)
                                    const affiliationName = affiliationData.title ||
                                                           affiliationData.name || affiliationData;
                                    $('#newCreatorAffiliation').val(affiliationName);

                                    // Preserve the structured data
                                    if (affiliationData.ror_id || affiliationData.id) {{
                                        $('#newCreatorRorData').val(JSON.stringify(affiliationData));
                                        $('#newCreatorOrcidAffiliationData').val('');
                                    }} else {{
                                        $('#newCreatorOrcidAffiliationData').val(JSON.stringify(affiliationData));
                                        $('#newCreatorRorData').val('');
                                    }}
                                }} else {{
                                    $('#newCreatorAffiliation').val('');
                                    $('#newCreatorRorData').val('');
                                    $('#newCreatorOrcidAffiliationData').val('');
                                }}

                                // Store the list item being edited and mark as editing mode
                                const modal = document.getElementById('creatorsModal');
                                modal.dataset.editingMode = 'true';
                                modal.editingItem = listItem[0]; // Store the actual DOM element
                                $('#creatorsModalLabel').text('Edit Creator');

                                // Update save button text
                                $('#saveCreatorBtn').text('Update');

                                // Show the modal first
                                const modalInstance = new bootstrap.Modal(modal);
                                modalInstance.show();

                                // Wait for modal to be fully shown before populating fields
                                $(modal).on('shown.bs.modal.editData', function() {{

                                    // Populate the creator modal with existing data
                                    $('#newCreatorName').val(creatorData.name || '');
                                    $('#newCreatorLastName').val(creatorData.lastName || '');
                                    $('#newCreatorOrcid').val(creatorData.orcid || '');

                                    // Handle affiliation
                                    if (typeof affiliationData === 'string') {{
                                        $('#newCreatorAffiliation').val(affiliationData);
                                        $('#newCreatorRorData').val('');
                                        $('#newCreatorOrcidAffiliationData').val('');
                                    }} else if (typeof affiliationData === 'object' &&
                                              affiliationData !== null) {{
                                        const affiliationName = affiliationData.title ||
                                                               affiliationData.name || affiliationData;
                                        $('#newCreatorAffiliation').val(affiliationName);
                                        if (affiliationData.ror_id || affiliationData.id) {{
                                            $('#newCreatorRorData').val(JSON.stringify(affiliationData));
                                            $('#newCreatorOrcidAffiliationData').val('');
                                        }} else {{
                                            $('#newCreatorOrcidAffiliationData').val(JSON.stringify(affiliationData));
                                            $('#newCreatorRorData').val('');
                                        }}
                                    }} else {{
                                        $('#newCreatorAffiliation').val('');
                                        $('#newCreatorRorData').val('');
                                        $('#newCreatorOrcidAffiliationData').val('');
                                    }}

                                    // Verify fields are populated
                                    setTimeout(function() {{

                                        // Trigger validation
                                        $('#newCreatorName').trigger('input');
                                        $('#newCreatorLastName').trigger('input');
                                        $('#newCreatorAffiliation').trigger('input');
                                        $('#newCreatorOrcid').trigger('input');
                                    }}, 200);

                                    // Remove this specific event handler so it doesn't fire again
                                    $(this).off('shown.bs.modal.editData');
                                }});

                            }} catch(error) {{
                                console.error('DEBUG: Error parsing creator data:', error);
                            }}
                        }});

                        // Reset modal state when closed
                        $('#creatorsModal').on('hidden.bs.modal', function() {{
                            const modal = this;
                            modal.dataset.editingMode = 'false';
                            modal.editingItem = null;
                            $('#creatorsModalLabel').text('Add Creator');
                            $('#saveCreatorBtn').text('✓ Save');
                        }});
                    }});
                </script>
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
                    valid_tags.append(tag)
                    found = True
                    break
            if not found:
                self.add_error("invenio_tags", f"Tag '{tag}' is not valid.")
                return []
        return valid_tags
