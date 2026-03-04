"""
Shared utilities for background tasks.

Use these from task modules to avoid duplicating logic across different task types.
"""

from __future__ import annotations


def resolve_app_image(app_instance) -> str | None:
    """
    Resolve the Docker/container image reference from an app instance.

    Supports different app types that store the image in different places:
    - Custom apps: `app_instance.image`
    - Jupyter/RStudio: `app_instance.environment.get_full_image_reference()`
    - Fallback: `app_instance.k8s_values["appconfig"]["image"]` if present

    Args:
        app_instance: A BaseAppInstance (or subclass) instance.

    Returns:
        The image reference string, or None if no image could be resolved.
    """
    image = getattr(app_instance, "image", None)
    if image:
        return image

    environment = getattr(app_instance, "environment", None)
    if environment and hasattr(environment, "get_full_image_reference"):
        env_image = environment.get_full_image_reference()
        if env_image:
            return env_image

    k8s_values = getattr(app_instance, "k8s_values", None) or {}
    if isinstance(k8s_values, dict):
        appconfig = k8s_values.get("appconfig") or {}
        if isinstance(appconfig, dict):
            k8s_image = appconfig.get("image")
            if k8s_image:
                return k8s_image

    return None
