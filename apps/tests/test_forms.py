import json
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.template import Context, Template
from django.test import TestCase
from sympy.physics.units import volume

from apps.forms import CustomAppForm
from apps.forms.dash import DashForm
from apps.forms.gradio import GradioForm
from apps.forms.shiny import ShinyForm
from apps.forms.streamlit import StreamlitForm
from apps.helpers import validate_path_k8s_label_compatible
from apps.models import (
    Apps,
    CustomAppInstance,
    K8sUserAppStatus,
    Subdomain,
    VolumeInstance,
)
from apps.models.app_types.custom.custom import validate_default_url_subpath
from projects.models import Flavor, PersistentVolumeMountPath, Project

User = get_user_model()

test_user = {"username": "foo1", "email": "foo@test.com", "password": "bar"}


class BaseAppFormTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(test_user["username"], test_user["email"], test_user["password"])
        self.project = Project.objects.create_project(name="test-perm", owner=self.user, description="")
        self.app = Apps.objects.create(name="Custom App", slug="customapp")
        self.volume = VolumeInstance.objects.create(
            name="project-vol",
            app=self.app,
            owner=self.user,
            project=self.project,
            size=1,
            subdomain=Subdomain.objects.create(subdomain="subdomain", project=self.project),
            k8s_user_app_status=K8sUserAppStatus.objects.create(),
        )
        self.flavor = Flavor.objects.create(name="flavor", project=self.project)


class CustomAppFormTest(BaseAppFormTest):
    def setUp(self):
        super().setUp()
        self.mount_path = PersistentVolumeMountPath.objects.create(
            volume=self.volume,
            mount_path="/home/data",
            is_default=True,
        )
        self.valid_data = {
            "name": "Valid Name",
            "description": "A valid description",
            "subdomain": "valid-subdomain",
            "mount_path": self.mount_path,
            "flavor": self.flavor,
            "access": "public",
            "source_code_url": "http://example.com",
            "note_on_linkonly_privacy": None,
            "port": 8000,
            "image": "mock.io/scilifelabdatacentre/image:tag",
            "default_url_subpath": "valid-default_url_subpath/",
            # These tags are found in the vocabulary service pickled data.
            "invenio_tags": "Antibodies|Chemistry|Cats",
        }

    def test_form_valid_data(self):
        form = CustomAppForm(self.valid_data, project_pk=self.project.pk)
        self.assertTrue(form.is_valid())

    def test_mount_path_maps_to_volume_and_path(self):
        form = CustomAppForm(self.valid_data, project_pk=self.project.pk)
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data["volume"], self.volume)
        self.assertEqual(form.cleaned_data["path"], self.mount_path.mount_path)

    def test_empty_mount_path_clears_volume_and_path(self):
        no_storage_data = self.valid_data.copy()
        no_storage_data["mount_path"] = ""

        form = CustomAppForm(no_storage_data, project_pk=self.project.pk)
        self.assertTrue(form.is_valid())
        self.assertIsNone(form.cleaned_data["volume"])
        self.assertEqual(form.cleaned_data["path"], "")

    def test_form_missing_data(self):
        invalid_data = self.valid_data.copy()
        invalid_data.pop("name")
        invalid_data.pop("port")
        invalid_data.pop("image")

        form = CustomAppForm(invalid_data, project_pk=self.project.pk)
        self.assertFalse(form.is_valid())
        self.assertIn("name", form.errors)
        self.assertIn("port", form.errors)
        self.assertIn("image", form.errors)

    # Path validation tests have been moved to test_storage_settings.py

    def test_invalid_subdomain(self):
        invalid_data = self.valid_data.copy()
        invalid_data["subdomain"] = "-some_invalid_subdomain!"

        form = CustomAppForm(invalid_data, project_pk=self.project.pk)
        self.assertFalse(form.is_valid())
        self.assertIn("Subdomain must be 3-53 characters long", str(form.errors))

    def test_source_url_enforced_when_public(self):
        invalid_data = self.valid_data.copy()
        invalid_data["source_code_url"] = ""

        form = CustomAppForm(invalid_data, project_pk=self.project.pk)
        self.assertFalse(form.is_valid())

    def test_link_only_note_enforced_when_link(self):
        invalid_data = self.valid_data.copy()
        invalid_data["access"] = "link"

        # Test no note
        form = CustomAppForm(invalid_data, project_pk=self.project.pk)
        self.assertFalse(form.is_valid())
        self.assertIn("Please, provide a reason for making the app accessible only via a link.", str(form.errors))

        # Now add a note
        valid_data = self.valid_data.copy()
        valid_data["access"] = "link"
        valid_data["note_on_linkonly_privacy"] = "A reason"
        form = CustomAppForm(valid_data, project_pk=self.project.pk)
        self.assertTrue(form.is_valid())

    @patch("apps.forms.base.InvenioClient")
    @patch("apps.forms.base.waffle.switch_is_active", return_value=True)
    def test_edit_form_prefills_language_and_funding_from_invenio(self, _mock_switch, mock_invenio_client):
        instance = CustomAppInstance.objects.create(
            app=self.app,
            chart="custom-app",
            owner=self.user,
            project=self.project,
            flavor=self.flavor,
            subdomain=Subdomain.objects.create(subdomain="existing-custom-app", project=self.project),
            k8s_user_app_status=K8sUserAppStatus.objects.create(),
            name="Existing app",
            description="Existing description",
            access="public",
            port=8000,
            image="ghcr.io/scilifelabdatacentre/image:tag",
            invenio_record_id="mock-record-id",
        )

        funding = [
            {
                "funder_id": "048a87296",
                "funder_name": "Uppsala University",
                "number": "grant-123",
                "title": "Grant title",
                "url": "https://example.org/grants/123",
            }
        ]
        mock_client = mock_invenio_client.return_value
        mock_client.get_record.return_value = {"metadata": {"languages": [{"id": "swe"}], "funding": []}}
        mock_client.extract_language_id.return_value = "swe"
        mock_client.extract_funding.return_value = funding

        form = CustomAppForm(project_pk=self.project.pk, instance=instance)

        self.assertEqual(form.fields["language"].initial, "swe")
        self.assertIn("funding_sources_json", form.fields)
        self.assertEqual(form.fields["funding_sources_json"].initial, json.dumps(funding))


class CustomAppFormRenderingTest(BaseAppFormTest):
    def setUp(self):
        super().setUp()
        self.valid_data = {
            "name": "Valid Name",
            "description": "A valid description",
            "subdomain": "valid-subdomain",
            "mount_path": "/home/user",  # Form uses mount_path instead of volume/path
            "flavor": self.flavor,
            "access": "public",
            "source_code_url": "http://example.com",
            "note_on_linkonly_privacy": None,
            "port": 8000,
            "image": "ghcr.io/scilifelabdatacentre/image:tag",
            # These tags are found in the vocabulary service pickled data.
            "invenio_tags": "Antibodies|Chemistry|Cats",
        }

    def test_form_rendering(self):
        valid_data = self.valid_data.copy()
        form = CustomAppForm(valid_data, project_pk=self.project.pk)

        template = Template("{% load crispy_forms_tags %}{% crispy form %}")
        context = Context({"form": form})
        rendered_form = template.render(context)
        for key, value in valid_data.items():
            if key == "invenio_tags":
                value = "Antibodies|Chemistry|Cats"
            if key == "mount_path":  # Form uses mount_path instead of volume
                value = self.valid_data.get("path")  # Mount path is same as path in the form
            if key == "flavor":
                value = self.flavor.name
            if key == "port":
                value = str(value)
            if value is None:
                continue

            self.assertIn(value, rendered_form)
            self.assertIn(f'name="{key}"', rendered_form)
            self.assertIn(f'id="id_{key}"', rendered_form)

        self.assertIn('value="project"', rendered_form)
        self.assertIn('value="private"', rendered_form)
        self.assertIn('value="link"', rendered_form)
        self.assertIn('value="public"', rendered_form)


class FundingFieldPresenceTest(BaseAppFormTest):
    funding_forms = [CustomAppForm, DashForm, GradioForm, ShinyForm, StreamlitForm]

    @patch("apps.forms.base.waffle.switch_is_active", return_value=True)
    def test_funding_field_present_when_doi_enabled(self, _mock_switch):
        for form_class in self.funding_forms:
            form = form_class(project_pk=self.project.pk)
            self.assertIn("funding_sources_json", form.fields, f"Missing funding field in {form_class.__name__}")

    @patch("apps.forms.base.waffle.switch_is_active", return_value=False)
    def test_funding_field_hidden_when_doi_disabled(self, _mock_switch):
        for form_class in self.funding_forms:
            form = form_class(project_pk=self.project.pk)
            self.assertNotIn(
                "funding_sources_json", form.fields, f"Funding field should be hidden in {form_class.__name__}"
            )


invalid_default_url_subpath_list = [
    "invalid space",
    'invalid_"_double_quote',
    "invalid_<_less_than_sign",
    "invalid_\\_backslash",
    "invalid_|_pipe",
    "invalid_^_caret",
    "invalid_{_left_curly_brace",
    "invalid_?_question_mark",
]

valid_default_url_subpath_list = [
    "valid_ÄÄ_unicode_charecters",
    "valid_aa/_forward_slash",
    "valid_____underscore",
    "_aa/bb/c_format",
    "valid_-_hiphen",
    "_ad-frt/fgh_cd_",
    "ÅÄaad1234",
]


@pytest.mark.parametrize("valid_default_url_subpath", valid_default_url_subpath_list)
def test_valid_default_url_subpath(valid_default_url_subpath):
    valid_check = True
    try:
        validate_default_url_subpath(valid_default_url_subpath)
    except ValidationError:
        valid_check = False

    assert valid_check


@pytest.mark.parametrize("invalid_default_url_subpath", invalid_default_url_subpath_list)
def test_invalid_default_url_subpath(invalid_default_url_subpath):
    valid_check = True
    try:
        validate_default_url_subpath(invalid_default_url_subpath)
    except ValidationError:
        valid_check = False

    assert not valid_check


invalid_shiny_site_dir_list = [
    "-invalidStart",  # Starts with a non-alphanumeric character
    "invalidEnd-",  # Ends with a non-alphanumeric character
    ".dotStart",  # Starts with a dot
    "dotEnd.",  # Ends with a dot
    "_underscoreStart",  # Starts with an underscore
    "underscoreEnd_",  # Ends with an underscore
    "label with spaces",  # Contains spaces
    "label@value",  # Contains an invalid character (@)
    "too_long_label_with_more_than_sixty_three_characters__1234567890",  # Exceeds 63 characters
    "just-dashes-",  # Ends with a dash
    "123#",  # Contains an invalid character (#)
    ".....",  # Only contains dots
    "-a",  # Starts with a dash
    "_a_",  # Starts and ends with underscores
    " ",  # Contains only whitespace
]

valid_shiny_site_dir_list = [
    "",  # Empty string is allowed
    "a",  # Single alphanumeric character
    "validLabel",  # Alphanumeric characters only
    "label-123",  # Contains a dash
    "label_with_underscores",  # Contains underscores
    "label.with.dots",  # Contains dots
    "abc-def_ghi.jkl",  # Contains all allowed special characters
    "label1",  # Ends with a number
    "1stLabel",  # Starts with a number
    "example-label",  # Simple example with a dash
    "nested.label.value",  # Dots between words
    "underscore_ending_label",  # Underscore in the middle
    "valid-value-0123",  # Contains numbers and special characters
    "long-valid-label-abcdefg-hijklmn-opqrstuv-wxyz",  # Long but within 63 characters
    "labelvalue123456789",  # Combination of letters and numbers
    "consecutive-dashes--allowed",  # Contains consecutive dashes
    "consecutive_underscores__allowed",  # Contains consecutive underscores
    "dots..in..between",  # Contains consecutive dots
    "mixed__--..label",  # Contains a mix of consecutive allowed characters
    "label---with---many---dashes",  # Multiple consecutive dashes in different parts
    "label..with..dots",  # Multiple consecutive dots in between
    "valid_--..mix_12",  # Combination of numbers, letters, and allowed characters
    "simple.label-value_1-2-3",  # Mixed with numbers, dots, underscores, and dashes
    "complex__label..value--mixed",  # A complex mix with all allowed characters in a consecutive manner
]


@pytest.mark.parametrize("valid_shiny_site_dir", valid_shiny_site_dir_list)
def test_valid_shiny_site_dir(valid_shiny_site_dir):
    valid_check = True
    try:
        validate_path_k8s_label_compatible(valid_shiny_site_dir)
    except ValidationError:
        valid_check = False

    assert valid_check


@pytest.mark.parametrize("invalid_shiny_site_dir", invalid_shiny_site_dir_list)
def test_invalid_shiny_site_dir(invalid_shiny_site_dir):
    valid_check = True
    try:
        validate_path_k8s_label_compatible(invalid_shiny_site_dir)
    except ValidationError:
        valid_check = False

    assert not valid_check
