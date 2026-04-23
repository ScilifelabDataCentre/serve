"""
Shared utilities for background tasks.

Use these from task modules to avoid duplicating logic across different task types.
"""

from __future__ import annotations


def select_latest_task_records(task_records):
    """
    Keep only the latest record for each logical task name.

    Background tasks may be retried or re-run across updates, so the UI and
    orchestration logic should reason about the latest record per task name
    rather than every historical row.
    """
    latest_by_name = {}
    for task_record in sorted(task_records, key=lambda task: (task.created_at, task.pk)):
        latest_by_name[task_record.task_name] = task_record

    return sorted(
        latest_by_name.values(),
        key=lambda task: (task.execution_order, task.created_at, task.pk),
    )


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


def resolve_app_access(app_instance) -> str | None:
    """
    Resolve the effective access level from an app instance.

    Some app types store access directly on the model, while others may only
    have the effective permission reflected in `k8s_values`.
    """
    access = getattr(app_instance, "access", None)
    if isinstance(access, str) and access:
        return access

    k8s_values = getattr(app_instance, "k8s_values", None) or {}
    if isinstance(k8s_values, dict):
        permission = k8s_values.get("permission")
        if isinstance(permission, str) and permission:
            return permission

    return None
