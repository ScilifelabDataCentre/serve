from django import forms
from django.conf import settings
from django_altcha import AltchaField

from common.forms import BootstrapErrorFormMixin


class TeachingRequestForm(BootstrapErrorFormMixin, forms.Form):
    """Form for submitting teaching requests."""

    name = forms.CharField(
        max_length=200,
        label="Your name",
        widget=forms.TextInput(attrs={"class": "form-control"}),
        required=True,
    )
    email = forms.EmailField(
        max_length=254,
        label="Your email address",
        widget=forms.EmailInput(attrs={"class": "form-control"}),
        required=True,
    )
    course_title = forms.CharField(
        max_length=200,
        label="Title of course/workshop/webinar",
        widget=forms.TextInput(attrs={"class": "form-control"}),
        required=False,
    )
    course_dates = forms.CharField(
        max_length=200,
        label="Date(s) and time(s) of course/workshop/webinar",
        widget=forms.TextInput(attrs={"class": "form-control"}),
        required=False,
    )
    course_description = forms.CharField(
        label="Description of course/workshop/webinar",
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 4}),
        required=True,
        help_text="Please provide information about what computational tools you will need for your training event, "
        "what hardware requirements you have, how many participants you expect, for how long the "
        "computational tools will need to stay available.",
    )
    captcha = AltchaField()

    required_css_class = "required"
