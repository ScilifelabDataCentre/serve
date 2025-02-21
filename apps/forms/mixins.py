import requests
from crispy_forms.layout import HTML, Div, Field, MultiField
from django import forms
from django.conf import settings


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

        # Ignore non-Docker images for now
        if "docker.io" not in image:
            return image

        # Split image into repository and tag
        if ":" in image:
            repository, tag = image.rsplit(":", 1)
        else:
            repository, tag = image, "latest"

        repository = repository.replace("docker.io/", "", 1)

        # Ensure repository is in the correct format
        # The request to Docker hub will fail otherwise
        if "/" not in repository:
            repository = f"library/{repository}"

        # Docker Hub API endpoint for checking the image
        docker_api_url = f"{settings.DOCKER_HUB_TAG_SEARCH}{repository}/tags/{tag}"

        try:
            response = requests.get(docker_api_url, timeout=5)
            if response.status_code != 200:
                self.add_error(
                    "image",
                    f"Docker image '{image}' is not publicly available on Docker Hub. "
                    "The URL you have entered may be incorrect, or the image might be private.",
                )
                return image
        except requests.RequestException:
            self.add_error("image", "Could not validate the Docker image. Please try again.")
            return image

        return image
