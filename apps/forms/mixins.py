import re

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

    def _validate_ghcr_image(self, image_url):
        """Validate that the GHCR image exists in packages of a user or an organisation."""
        # regex match:
        # ghcr\.io/ - ghcr.io
        # (?P) used to capture a named group eg. owner, image and tag
        # [\w-]+ allow more than 1 character of letters, numbers underscores and hyphens
        match = re.match(r"ghcr\.io/(?P<owner>[\w-]+)/(?P<image>[\w-]+):(?P<tag>[\w.-]+)", image_url)
        if not match:
            return False

        owner, image, tag = match.group("owner"), match.group("image"), match.group("tag")
        url_user = f"https://api.github.com/users/{owner}/packages/container/{image}/versions"
        url_org = f"https://api.github.com/orgs/{owner}/packages/container/{image}/versions"

        headers = {"Authorization": f"Bearer {settings.GITHUB_TOKEN}", "Accept": "application/vnd.github+json"}

        # TODO Using a nested for-loop for better readability, improve this code if possible
        for url in (url_user, url_org):
            response = requests.get(url, headers=headers)
            if response.status_code == 200:
                versions = response.json()
                for version in versions:
                    container_tags = version["metadata"]["container"].get("tags", [])
                    if (container_tags) and (tag in container_tags):
                        return True

        return False

    def clean_image(self):
        """Validate the container image input."""
        image = self.cleaned_data.get("image", "").strip()
        if not image:
            self.add_error("image", "Container image field cannot be empty.")
            return image

        if "ghcr.io" in image:
            if not self._validate_ghcr_image(image):
                self.add_error("image", "Could not find the image on GHCR. Please try again.")
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
