from django import forms
from django.contrib.auth import get_user_model

from .validators import validate_image_content_type

User = get_user_model()


class TransferProjectOwnershipForm(forms.Form):
    transfer_to = forms.CharField(label="New project owner", max_length=256)


class PublishProjectToGitHub(forms.Form):
    user_name = forms.CharField(label="GitHub username", max_length=256)
    user_password = forms.CharField(label="GitHub password", widget=forms.PasswordInput(), max_length=256)


class GrantAccessForm(forms.Form):
    platform_users = []  # type: ignore

    def __init__(self, *args, **kwargs):
        super(GrantAccessForm, self).__init__(*args, **kwargs)
        self.platform_users = User.objects.all()

    OPTIONS = []
    for user in platform_users:
        OPTIONS.append((user.pk, user.username))

    selected_users = forms.MultipleChoiceField(widget=forms.SelectMultiple, choices=OPTIONS)


# Note: 2024-09-30: I don't think we're currently using this one but will keep it up to date for future.
class FlavorForm(forms.Form):
    cpu_req = forms.CharField(label="CPU request", max_length=10, initial="200m")
    mem_req = forms.CharField(label="Memory request", max_length=15, initial="0.5Gi")
    ephmem_req = forms.CharField(label="Ephemeral storage request", max_length=15, initial="200Mi")

    cpu_lim = forms.CharField(label="CPU limit", max_length=10, initial="2000m")
    mem_lim = forms.CharField(label="Memory limit", max_length=15, initial="4Gi")
    ephmem_req = forms.CharField(label="Ephemeral storage limit", max_length=15, initial="5000Mi")


class ImageUpdateForm(forms.Form):
    image = forms.ImageField(validators=[validate_image_content_type])
