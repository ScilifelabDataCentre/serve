from typing import List

import requests
from django.conf import settings


def fetch_docker_hub_images_and_tags(query: str) -> List[str]:
    """
    Fetch Docker images and latest tags matching a query.
    This function fetches images with the highest pull count.
    """
    image_search_url = f"{settings.DOCKER_HUB_IMAGE_SEARCH}?query={query}"
    try:
        response = requests.get(image_search_url, timeout=3)
        response.raise_for_status()
        results = response.json().get("results", [])
    except requests.RequestException:
        return []

    # Sort images by pull count
    sorted_results = sorted(results, key=lambda x: x.get("pull_count", 0), reverse=True)

    images = []
    # Use the top 5 images
    for repo in sorted_results[:5]:
        repo_name = repo["repo_name"]

        # Fetch available tags
        tags_search_url = f"{settings.DOCKER_HUB_TAG_SEARCH}{repo_name}/tags/?page_size=3"
        try:
            tag_response = requests.get(tags_search_url, timeout=2)
            tag_response.raise_for_status()
            tags = [tag["name"] for tag in tag_response.json().get("results", [])]
        except requests.RequestException:
            # Default to latest if tags cannot be fetched
            tags = ["latest"]

        for tag in tags:
            images.append(f"docker.io/{repo_name}:{tag}")

    return images
