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


def fetch_ghcr_images_and_tags(token: str, query: str) -> List[str]:
    """
    Fetch container images and latest tags from GitHub Container Registry (GHCR).
    The fetched data is found in the SciLifeLab Data Centre organisation.
    Requires a GitHub access token with `read:packages` scope.
    """
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}

    try:
        response = requests.get(settings.GHCR_IMAGE_SEARCH, headers=headers)
        response.raise_for_status()
        results = response.json()
    except requests.RequestException:
        return []

    query_hits = []
    # Keep images that contain query string
    for image in results:
        image_name = image["name"]
        if query in image_name:
            query_hits.append(image_name)

    ghcr_images = []
    # Get tags of query hits
    for hit in query_hits:
        tags_url = f"{settings.GHCR_TAG_SEARCH}/{hit}/versions"
        try:
            tag_response = requests.get(tags_url, headers=headers)
            tag_response.raise_for_status()
            result = tag_response.json()
            tag_hit = result[0]
            tags = tag_hit["metadata"]["container"]["tags"]
        except requests.RequestException:
            tags = ["latest"]

        for tag in tags:
            ghcr_images.append(f"ghcr.io/scilifelabdatacentre/{hit}:{tag}")

    return ghcr_images
