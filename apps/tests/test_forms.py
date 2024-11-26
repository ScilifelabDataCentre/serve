import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.template import Context, Template
from django.test import TestCase

from apps.forms import CustomAppForm
from apps.models import Apps, AppStatus, Subdomain, VolumeInstance
from apps.models.app_types.custom.custom import validate_default_url_subpath
from apps.models.app_types.shiny import validate_shiny_site_dir
from projects.models import Flavor, Project

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
            app_status=AppStatus.objects.create(status="Created"),
        )
        self.flavor = Flavor.objects.create(name="flavor", project=self.project)


class CustomAppFormTest(BaseAppFormTest):
    def setUp(self):
        super().setUp()
        self.valid_data = {
            "name": "Valid Name",
            "description": "A valid description",
            "subdomain": "valid-subdomain",
            "volume": self.volume,
            "path": "/home/user",
            "flavor": self.flavor,
            "access": "public",
            "source_code_url": "http://example.com",
            "note_on_linkonly_privacy": None,
            "port": 8000,
            "image": "ghcr.io/scilifelabdatacentre/image:tag",
            "tags": ["tag1", "tag2", "tag3"],
            "default_url_subpath": "valid-default_url_subpath/",
        }

    def test_form_valid_data(self):
        form = CustomAppForm(self.valid_data, project_pk=self.project.pk)
        self.assertTrue(form.is_valid())

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

    def test_invalid_path(self):
        invalid_data = self.valid_data.copy()
        invalid_data["path"] = "/var"

        form = CustomAppForm(invalid_data, project_pk=self.project.pk)
        self.assertFalse(form.is_valid())
        self.assertIn("Path must start with", str(form.errors))

    def test_valid_path_if_set_in_admin_panel(self):
        valid_data = self.valid_data.copy()
        form = CustomAppForm(valid_data, project_pk=self.project.pk)
        self.assertTrue(form.is_valid())

        # Simulate a path set in the admin panel
        instance = form.save(commit=False)
        instance.project = self.project
        instance.owner = self.user
        instance.app_status = AppStatus.objects.create(status="Created")
        instance.app = self.app

        # Fetch subdomain and set
        subdomain_name, is_created_by_user = form.cleaned_data.get("subdomain")
        subdomain, _ = Subdomain.objects.get_or_create(
            subdomain=subdomain_name, project=self.project, is_created_by_user=is_created_by_user
        )
        instance.subdomain = subdomain

        # Change the path to something that the form would not allow
        instance.path = "/var"
        instance.save()

        # Open form in "edit mode" by sending instance as argument
        form = CustomAppForm(valid_data, project_pk=self.project.pk, instance=instance)

        # This should now work, since we set the path in the "admin panel"
        self.assertTrue(form.is_valid())

    def test_volume_no_path(self):
        invalid_data = self.valid_data.copy()
        invalid_data.pop("path")

        form = CustomAppForm(invalid_data, project_pk=self.project.pk)
        self.assertFalse(form.is_valid())
        self.assertIn("Path is required when volume is selected.", str(form.errors))

    def test_path_no_volume(self):
        invalid_data = self.valid_data.copy()
        invalid_data.pop("volume")

        form = CustomAppForm(invalid_data, project_pk=self.project.pk)
        self.assertFalse(form.is_valid())
        self.assertIn("Warning, you have provided a path, but not selected a volume.", str(form.errors))

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


class CustomAppFormRenderingTest(BaseAppFormTest):
    def setUp(self):
        super().setUp()
        self.valid_data = {
            "name": "Valid Name",
            "description": "A valid description",
            "subdomain": "valid-subdomain",
            "volume": self.volume,
            "path": "/home/user",
            "flavor": self.flavor,
            "access": "public",
            "source_code_url": "http://example.com",
            "note_on_linkonly_privacy": None,
            "port": 8000,
            "image": "ghcr.io/scilifelabdatacentre/image:tag",
            "tags": ["tag1", "tag2", "tag3"],
        }

    def test_form_rendering(self):
        valid_data = self.valid_data.copy()
        form = CustomAppForm(valid_data, project_pk=self.project.pk)

        template = Template("{% load crispy_forms_tags %}{% crispy form %}")
        context = Context({"form": form})
        rendered_form = template.render(context)
        for key, value in valid_data.items():
            if key == "tags":
                value = "".join(tag for tag in key)
            if key == "volume":
                value = self.volume.name
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
        validate_shiny_site_dir(valid_shiny_site_dir)
    except ValidationError:
        valid_check = False

    assert valid_check


@pytest.mark.parametrize("invalid_shiny_site_dir", invalid_shiny_site_dir_list)
def test_invalid_shiny_site_dir(invalid_shiny_site_dir):
    valid_check = True
    try:
        validate_shiny_site_dir(invalid_shiny_site_dir)
    except ValidationError:
        valid_check = False

    assert not valid_check
