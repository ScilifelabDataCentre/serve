import json
import logging
import uuid

import waffle
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Button, Div, Submit
from django import forms
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.forms import Select, SelectMultiple
from django.shortcuts import get_object_or_404

from apps.forms.field.widget import SubdomainInputGroup
from apps.models import BaseAppInstance, Subdomain, VolumeInstance
from apps.types_.subdomain import SubdomainCandidateName, SubdomainTuple
from doi_minting.services.invenio_svc import InvenioService
from projects.models import Flavor, Project

logger = logging.getLogger(__name__)

__all__ = ["BaseForm", "AppBaseForm"]


class BaseForm(forms.ModelForm):
    """The most generic form for apps running on serve. Current intended use is for VolumesK8S type apps"""

    subdomain = forms.CharField(
        required=False,
        min_length=3,
        max_length=53,
        widget=SubdomainInputGroup(base_widget=forms.TextInput, data={}),
    )
    LANGUAGE_CHOICES = [
        ("eng", "English"),
        ("swe", "Swedish"),
        ("und", "Other"),
    ]

    def __init__(self, *args, **kwargs):
        self.project_pk = kwargs.pop("project_pk", None)
        self.request = kwargs.pop("request", None)  # Store request for mixins
        self.project = get_object_or_404(Project, pk=self.project_pk) if self.project_pk else None
        self.model_name = self._meta.model._meta.verbose_name.replace("Instance", "")
        self._metadata_fetch_failed = False

        super().__init__(*args, **kwargs)

        self._setup_form_fields()
        self.add_metadata()

        # Prevent form from opening if metadata fetch failed
        if self._metadata_fetch_failed:
            raise PermissionDenied(
                "This app cannot be edited due to a system error while fetching metadata. "
                "Please contact support for assistance."
            )

        self._setup_form_helper()
        for field in self.fields.values():
            if isinstance(field.widget, (Select, SelectMultiple)):
                field.widget.attrs["class"] = "form-select"
            else:
                field.widget.attrs["class"] = "form-control"

    # restore helptext for model in case it is rest in form
    def _restore_model_help_text(self):
        for name, field in self.fields.items():
            # Only for model-backed fields
            if name in getattr(self._meta, "fields", []):
                model_field = self._meta.model._meta.get_field(name)
                if not field.help_text and getattr(model_field, "help_text", ""):
                    field.help_text = model_field.help_text

    def _setup_form_fields(self):
        # Populate subdomain field with instance subdomain if it exists
        self.fields["subdomain"].widget.data["project_pk"] = self.project_pk
        self.fields["subdomain"].widget.data["hidden"] = "hidden"
        self.fields["subdomain"].initial = ""
        if self.instance and self.instance.pk:
            self.fields["subdomain"].initial = self.instance.subdomain.subdomain if self.instance.subdomain else ""
            self.fields["subdomain"].widget.data["hidden"] = ""

        # Handle name
        self.fields["name"].initial = ""
        # Initialize subjects_keywords field to existing JSON data or empty list
        if self.instance and self.instance.pk and hasattr(self.instance, "subjects_keywords"):
            self.instance.refresh_from_db()
            self._original_subjects_keywords = self.instance.subjects_keywords or []
        else:
            self._original_subjects_keywords = []

        self._restore_model_help_text()

    def _setup_form_helper(self):
        # Create a footer for submit form or cancel
        self.footer = Div(
            Button(
                "cancel",
                "Cancel",
                css_class="btn-outline-dark btn-outline-cancel me-2",
                onclick="window.history.back()",
            ),
            Submit("submit", "Submit"),
            css_class="card-footer d-flex justify-content-end",
        )
        self.helper = FormHelper(self)
        self.helper.attrs = {
            "class": "needs-validation",
            "novalidate": "novalidate",
        }
        # Ensure HTML5 `required` attributes are rendered
        self.helper.use_required_attribute = True
        self.helper.form_method = "post"

    def add_metadata(self):
        instance = getattr(self, "instance", None)
        if not instance or not getattr(instance, "pk", None):
            return

        # Only proceed if instance has Invenio-related attributes (skip for VolumeInstance, etc.)
        if not hasattr(instance, "access") or not hasattr(instance, "invenio_record_id"):
            logger.debug(
                f"Skipping metadata fetch - instance {type(instance).__name__} doesn't have required Invenio attributes"
            )
            return

        # Fetch metadata for public app from Invenio
        if not instance.invenio_record_id:
            logger.info("Skipping metadata fetch from Invenio for app without Invenio record ID.")
            return

        record_id = getattr(instance, "invenio_record_id", None)
        if not record_id:
            return

        try:
            logger.info(f"Fetching metadata from Invenio for record ID {record_id} to populate form initial values.")
            invenio_svc = InvenioService()
            record = invenio_svc.get_current_record_data(record_id)
            app_metadata = invenio_svc.extract_app_metadata(record)

            # Extract language from Invenio metadata
            if "language" in self.fields:
                extracted_language = invenio_svc.extract_language_id(app_metadata)
                logger.info(
                    f"Raw extracted language from Invenio: {extracted_language} (type: {type(extracted_language)})"
                )

                # Handle if extracted_language is a dict with title key
                if isinstance(extracted_language, dict):
                    language_code = extracted_language.get("id", extracted_language.get("title", ""))
                    logger.info(f"Extracted language dict: {extracted_language}, using code: {language_code}")
                else:
                    language_code = extracted_language or ""
                    logger.info(f"Extracted language string: '{language_code}'")

                self.fields["language"].initial = language_code
                logger.info(f"Final language mapping: {language_code}")

            # Extract funding from Invenio metadata
            funding = invenio_svc.extract_funding(app_metadata)
            logger.info(f"Extracted funding from Invenio: {funding} (type: {type(funding)})")
            if "funding_sources_json" in self.fields:
                logger.info("funding_sources_json field exists in form")
                # Convert Pydantic Funding objects to flat structure
                funding_data = []
                if funding is not None:
                    for f in funding:
                        fd = f.model_dump()
                        funder = fd.get("funder") or {}
                        award = fd.get("award") or {}

                        # Extract title from award (handle dict or string)
                        title = award.get("title", "")
                        if isinstance(title, dict):
                            title = title.get("en", title.get("eng", ""))

                        funding_data.append(
                            {
                                "funder_id": funder.get("id", ""),
                                "funder_name": funder.get("name", ""),
                                "number": award.get("number", ""),
                                "title": title or "",
                                "url": award.get("url", ""),
                            }
                        )

                    logger.info(f"Converted funding to flattened data: {funding_data}")
                else:
                    logger.info("No funding data found")
                funding_json = json.dumps(funding_data)
                logger.info(f"Setting funding_sources_json initial value: {funding_json}")
                self.fields["funding_sources_json"].initial = funding_json
            else:
                logger.info("funding_sources_json field NOT found in form")

            # Extract creators from Invenio metadata
            creators = invenio_svc.extract_creators(app_metadata)
            logger.info(f"Extracted creators from Invenio: {creators} (type: {type(creators)})")
            logger.info(f"'creators' field exists in form: {'creators' in self.fields}")

            # Store creators data for CreatorsMixin to use
            if creators:
                self._invenio_creators = creators
                logger.info(f"Stored {len(creators)} creators for CreatorsMixin to use")
            else:
                self._invenio_creators = []
                logger.info("No creators found in Invenio metadata")

            # Extract related publications from Invenio metadata
            related_publications = invenio_svc.extract_related_publications(app_metadata)
            logger.info(
                "Extracted related publications from Invenio: %s (type: %s)",
                related_publications,
                type(related_publications),
            )

            if "related_publications_json" in self.fields:
                related_publications_data = [
                    {
                        "doi": publication.doi,
                        "publication_type": publication.publication_type,
                    }
                    for publication in related_publications
                ]

                self.fields["related_publications_json"].initial = json.dumps(related_publications_data)

        except Exception:
            logger.exception("Failed to fetch metadata from Invenio; leaving default initial values.")
            self._metadata_fetch_failed = True

        # Re-initialize creators after metadata extraction if CreatorsMixin is being used
        if hasattr(self, "_initialize_creators"):
            self._initialize_creators()
            logger.info("Re-initialized creators after Invenio metadata extraction")

    def clean_subdomain(self):
        cleaned_data = super().clean()
        subdomain_input = cleaned_data.get("subdomain")
        return self.validate_subdomain(subdomain_input)

    def clean_source_code_url(self):
        cleaned_data = super().clean()
        access = cleaned_data.get("access")
        source_code_url = cleaned_data.get("source_code_url")

        if access == "public" and not source_code_url:
            self.add_error("source_code_url", "Source is required when access is public.")

        return source_code_url

    def clean_note_on_linkonly_privacy(self):
        cleaned_data = super().clean()

        access = cleaned_data.get("access", None)
        note_on_linkonly_privacy = cleaned_data.get("note_on_linkonly_privacy", None)

        if access == "link" and not note_on_linkonly_privacy:
            self.add_error(
                "note_on_linkonly_privacy", "Please, provide a reason for making the app accessible only via a link."
            )

        return note_on_linkonly_privacy

    def clean_subjects_keywords(self):
        raw = self.cleaned_data.get("subjects_keywords") or []

        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except json.JSONDecodeError as e:
                raise forms.ValidationError("Invalid subjects/keywords data.") from e

        if not isinstance(raw, list):
            raise forms.ValidationError("Subjects/keywords must be a list.")

        cleaned_subjects_keywords = []

        for item in raw:
            if not isinstance(item, dict):
                raise forms.ValidationError("Each subject/keyword entry must be an object.")

            subject = (item.get("subject") or "").strip()
            subject_scheme = (item.get("subject_scheme") or "").strip()
            classification_code = (item.get("classification_code") or "").strip()

            if not subject:
                raise forms.ValidationError("Each subject/keyword entry must have a subject.")
            if not subject_scheme:
                raise forms.ValidationError("Each subject/keyword entry must have a scheme.")
            if not classification_code:
                raise forms.ValidationError("Each subject/keyword entry must have an identifier.")

            cleaned_subjects_keywords.append(
                {
                    "subject": subject,
                    "subject_scheme": subject_scheme,
                    "classification_code": classification_code,
                }
            )

        return cleaned_subjects_keywords

    def clean_funding_sources_json(self):
        raw = self.cleaned_data.get("funding_sources_json") or "[]"
        try:
            data = json.loads(raw) if isinstance(raw, str) else raw
        except json.JSONDecodeError as e:
            raise forms.ValidationError("Invalid funding sources data.") from e

        if not isinstance(data, list):
            raise forms.ValidationError("Funding sources must be a list.")

        for item in data:
            if not isinstance(item, dict):
                raise forms.ValidationError("Invalid funding source entry.")

            funder_name = (item.get("funder_name") or "").strip()
            funder_id = (item.get("funder_id") or "").strip()

            if not funder_name:
                raise forms.ValidationError("Each funding source must have a funder name.")
            if not funder_id:
                raise forms.ValidationError("Each funding source must be selected from the Invenio funders list.")

        return json.dumps(data)

    def clean_related_publications_json(self):
        raw = self.cleaned_data.get("related_publications_json") or "[]"

        try:
            data = json.loads(raw) if isinstance(raw, str) else raw
        except json.JSONDecodeError as e:
            raise forms.ValidationError("Invalid related publications data.") from e

        if not isinstance(data, list):
            raise forms.ValidationError("Related publications must be a list.")

        cleaned = []

        for item in data:
            if not isinstance(item, dict):
                raise forms.ValidationError("Invalid related publication entry.")

            doi = (item.get("doi") or "").strip()
            publication_type = (item.get("publication_type") or "").strip()

            if not doi:
                raise forms.ValidationError("Each related publication must have a DOI.")
            if not doi.startswith("https://doi.org/") or doi == "https://doi.org/":
                raise forms.ValidationError("Publication DOI must start with https://doi.org/ and include a DOI value.")
            if not publication_type:
                raise forms.ValidationError("Each related publication must have a publication type.")

            cleaned.append(
                {
                    "doi": doi,
                    "publication_type": publication_type,
                }
            )

        return json.dumps(cleaned)

    def validate_subdomain(self, subdomain_input):
        # If user did not input subdomain, set it to our standard release name
        if not subdomain_input:
            subdomain = "r" + uuid.uuid4().hex[0:8]
            if Subdomain.objects.filter(subdomain=subdomain_input).exists():
                error_message = "Wow, you just won the lottery. Contact us for a free chocolate bar."
                raise forms.ValidationError(error_message)
            return SubdomainTuple(subdomain, False)

        # Check if the instance has an existing subdomain
        current_subdomain = getattr(self.instance, "subdomain", None)

        # Validate if the subdomain input matches the instance's current subdomain
        if current_subdomain and current_subdomain.subdomain == subdomain_input:
            return SubdomainTuple(subdomain_input, current_subdomain.is_created_by_user)

        # Convert the subdomain to lowercase. OK because we force convert to lowecase in the UI.
        subdomain_input = subdomain_input.lower()

        # Check if the subdomain adheres to helm rules
        subdomain_candidate = SubdomainCandidateName(subdomain_input, self.project_pk)

        try:
            subdomain_candidate.validate_subdomain()
        except forms.ValidationError as e:
            raise forms.ValidationError(f"{e.message}")

        # Check for subdomain availability
        if not subdomain_candidate.is_available():
            error_message = "Subdomain already exists. Please choose another one."
            raise forms.ValidationError(error_message)

        return SubdomainTuple(subdomain_input, True)

    @property
    def changed_data(self):
        """Override changed_data to handle fields that are falsely flagged as changed."""
        changed_data = super().changed_data.copy() if hasattr(super(), "changed_data") else []

        # Handle creators field - compare JSON data to avoid false positives
        if "creators" in changed_data and self.instance and self.instance.pk:
            try:
                import json

                # Get submitted data (from POST or default)
                current_creators = self.data.get("creators", "[]")
                # If creators is a list in data (e.g. from some client), use it directly
                current_data = current_creators if isinstance(current_creators, list) else json.loads(current_creators)

                # Get initial data from the field
                initial_creators = self.fields["creators"].initial or "[]"
                initial_data = initial_creators if isinstance(initial_creators, list) else json.loads(initial_creators)

                # Normalize data structures for comparison
                def normalize(data):
                    norm = []
                    for creator in data:
                        if not isinstance(creator, dict):
                            norm.append(creator)
                            continue

                        # Extract affiliation - handle both string and structured ROR/ORCID data
                        aff = creator.get("affiliation", "")
                        if isinstance(aff, dict):
                            aff_name = (aff.get("name") or aff.get("title") or "").strip()
                        else:
                            aff_name = str(aff).strip()

                        norm.append(
                            {
                                "name": (creator.get("name") or "").strip(),
                                "lastName": (creator.get("lastName") or "").strip(),
                                "orcid": (creator.get("orcid") or "").strip(),
                                "affiliation": aff_name,
                            }
                        )
                    return norm

                current_norm = normalize(current_data)
                initial_norm = normalize(initial_data)

                # If the data is the same, remove from changed_data
                if current_norm == initial_norm:
                    changed_data.remove("creators")
            except (json.JSONDecodeError, KeyError, ValueError):
                # If there's an error parsing, keep the field in changed_data to be safe
                pass

        # Handle path field - compare current value with initial form value
        if "path" in changed_data and self.instance and self.instance.pk:
            try:
                current_path = self.data.get("path", "") or ""
                initial_path = self.fields["path"].initial or ""

                # If the paths are the same, remove from changed_data
                if current_path == initial_path:
                    changed_data.remove("path")
            except (AttributeError, KeyError):
                # If there's an error, keep the field in changed_data to be safe
                pass

        # Handle subjects_keywords field - compare JSON data
        if "subjects_keywords" in changed_data and self.instance and self.instance.pk:
            try:
                current_subjects_keywords = self.data.get("subjects_keywords", "") or "[]"
                initial_subjects_keywords = self.fields["subjects_keywords"].initial or "[]"

                current_data = (
                    json.loads(current_subjects_keywords)
                    if isinstance(current_subjects_keywords, str)
                    else current_subjects_keywords
                )
                initial_data = (
                    json.loads(initial_subjects_keywords)
                    if isinstance(initial_subjects_keywords, str)
                    else initial_subjects_keywords
                )

                # If the data is the same, remove from changed_data
                if current_data == initial_data:
                    changed_data.remove("subjects_keywords")
            except (json.JSONDecodeError, KeyError, ValueError, TypeError):
                # If there's an error parsing, keep the field in changed_data to be safe
                pass

        # Handle language field - compare current value with initial form value
        if "language" in changed_data and self.instance and self.instance.pk:
            try:
                current_language = self.data.get("language", "") or ""
                initial_language = self.fields["language"].initial or ""

                # For form-only fields (not stored in model), if form data is missing but field has initial,
                # treat missing as initial value (not changed)
                if not hasattr(self.instance, "language") and current_language == "" and initial_language:
                    # Missing form data should be treated as initial value
                    changed_data.remove("language")
                elif current_language == initial_language:
                    # Values are the same, so no change
                    changed_data.remove("language")
            except (AttributeError, KeyError):
                # If there's an error, keep the field in changed_data to be safe
                pass

        # Handle funding_sources_json field - compare JSON data
        if "funding_sources_json" in changed_data and self.instance and self.instance.pk:
            try:
                import json

                current_funding = self.data.get("funding_sources_json", "") or "[]"
                initial_funding = self.fields["funding_sources_json"].initial or "[]"

                # Parse both JSON strings and compare the data structures
                current_data = json.loads(current_funding) if current_funding else []
                initial_data = json.loads(initial_funding) if initial_funding else []

                # If the data is the same, remove from changed_data
                if current_data == initial_data:
                    changed_data.remove("funding_sources_json")
            except (json.JSONDecodeError, KeyError, ValueError):
                # If there's an error parsing, keep the field in changed_data to be safe
                pass

        # Handle related publications - compare JSON data
        if "related_publications_json" in changed_data and self.instance and self.instance.pk:
            try:
                import json

                current_publications = self.data.get("related_publications_json", "") or "[]"
                initial_publications = self.fields["related_publications_json"].initial or "[]"

                # Parse both JSON strings and compare the data structures
                current_data = json.loads(current_publications) if current_publications else []
                initial_data = json.loads(initial_publications) if initial_publications else []

                # If the data is the same, remove from changed_data
                if current_data == initial_data:
                    changed_data.remove("related_publications_json")
            except (json.JSONDecodeError, KeyError, ValueError):
                # If there's an error parsing, keep the field in changed_data to be safe
                pass

        # Handle volume field - compare current value with initial form value
        if "volume" in changed_data and self.instance and self.instance.pk:
            try:
                current_volume = self.data.get("volume", "") or ""
                initial_volume = str(self.fields["volume"].initial or "")

                # If the volumes are the same, remove from changed_data
                if current_volume == initial_volume:
                    changed_data.remove("volume")
            except (AttributeError, KeyError):
                # If there's an error, keep the field in changed_data to be safe
                pass

        return changed_data

    class Meta:
        # Specify model to be used
        model = BaseAppInstance
        fields = "__all__"


class AppBaseForm(BaseForm):
    """
    Generic form for apps that require some compute power,
    so you can treat this form as an actual base form for the most of the apps
    """

    volume = forms.ModelChoiceField(
        queryset=VolumeInstance.objects.none(), required=False, empty_label="None", initial=None
    )

    flavor = forms.ModelChoiceField(queryset=Flavor.objects.none(), required=True, empty_label=None)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def _setup_form_fields(self):
        super()._setup_form_fields()
        flavor_queryset = (
            Flavor.objects.filter(project__pk=self.project_pk) if self.project_pk else Flavor.objects.none()
        )
        # Handle Flavor field
        self.fields["flavor"].label = "Hardware"
        self.fields["flavor"].queryset = flavor_queryset
        self.fields["flavor"].initial = flavor_queryset.first()  # if flavor_queryset else None

        # Handle Access field
        self.fields["access"].label = "Permission"

        self.fields["subdomain"].help_text = "Choose subdomain, create a new one or leave blank to get a random one."
