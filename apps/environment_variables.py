"""Validation and Kubernetes conversion for private application environment settings."""

import json
import re

from django.core.exceptions import ValidationError

ENVIRONMENT_APP_SLUGS = frozenset({"customapp", "dashapp", "gradio", "streamlit", "shinyapp", "shinyproxyapp"})
ENVIRONMENT_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,252}\Z")
SECRET_NAME = re.compile(r"[a-z0-9](?:[-a-z0-9]*[a-z0-9])?(?:\.[a-z0-9](?:[-a-z0-9]*[a-z0-9])?)*\Z")


def validate_kubernetes_secret_name(name):
    if (
        not isinstance(name, str)
        or len(name) > 253
        or not SECRET_NAME.fullmatch(name)
        or any(len(part) > 63 for part in name.split("."))
    ):
        raise ValidationError("Use a lowercase Secret name with DNS components of at most 63 characters.")


def validate_environment_variables(value):
    """Accept only ordinary string values, never credentials or pod settings."""
    if not isinstance(value, dict):
        raise ValidationError("Environment variables must be a JSON object.")
    if len(value) > 100 or len(json.dumps(value).encode("utf-8")) > 65536:
        raise ValidationError("Use at most 100 environment variables and 64 KiB of configuration.")
    for name, source in value.items():
        if not isinstance(name, str) or not ENVIRONMENT_NAME.fullmatch(name):
            raise ValidationError(
                "Variable names must start with a letter or underscore and contain letters, digits, or underscores."
            )
        if not isinstance(source, dict) or set(source) != {"value"}:
            raise ValidationError("Each configuration variable must contain one value.")
        if not isinstance(source["value"], str) or "\x00" in source["value"]:
            raise ValidationError("Environment variable values must be strings without null characters.")


def validate_environment_secret_imports(value):
    if not isinstance(value, list) or len(value) > 100:
        raise ValidationError("Choose at most 100 Secrets.")
    try:
        encoded = json.dumps(value).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValidationError("Invalid Secret selection.") from exc
    if len(encoded) > 65536:
        raise ValidationError("Secret selections must fit within 64 KiB.")
    names = set()
    for selection in value:
        if not isinstance(selection, dict) or set(selection) not in ({"name", "all"}, {"name", "keys"}):
            raise ValidationError("Select either all keys or specific keys for each Secret.")
        name = selection["name"]
        if not isinstance(name, str) or name in names:
            raise ValidationError("Secret selections must use unique Secret names.")
        names.add(name)
        validate_kubernetes_secret_name(name)
        if "all" in selection:
            if selection["all"] is not True:
                raise ValidationError("All keys must be selected explicitly.")
        else:
            if not selection["keys"]:
                raise ValidationError("Choose at least one Secret key.")
            validate_approved_secret_keys(selection["keys"])


def validate_approved_secret_keys(value):
    if not isinstance(value, list) or len(value) > 100:
        raise ValidationError("List at most 100 Secret keys.")
    if not all(isinstance(key, str) and ENVIRONMENT_NAME.fullmatch(key) for key in value):
        raise ValidationError("Secret keys must use valid environment variable names.")
    if len(set(value)) != len(value):
        raise ValidationError("Secret keys must be unique.")


def validate_environment_configuration(value, *, is_shiny=False):
    validate_environment_variables(value)
    if is_shiny:
        for name, source in value.items():
            if name.startswith("SHINYPROXY_"):
                raise ValidationError("Names beginning with SHINYPROXY_ are reserved for ShinyProxy.")
            if any(marker in source["value"] for marker in ("#{", "${")):
                raise ValidationError(
                    "Shiny environment values cannot contain Spring expressions (#{ or ${). "
                    "Use a Secret reference for these values."
                )


def validate_project_secret_imports(secret_imports, project_id, *, is_shiny=False):
    """Return the approved variable names supplied by selected Secret keys."""
    from apps.models import AppEnvironmentSecret

    validate_environment_secret_imports(secret_imports)
    selected_names = set()
    if secret_imports:
        approved = dict(AppEnvironmentSecret.objects.filter(project_id=project_id).values_list("name", "keys"))
        for selection in secret_imports:
            if selection["name"] not in approved:
                raise ValidationError("Select only Secrets approved by an administrator for this project.")
            if "all" in selection:
                keys = approved[selection["name"]]
            else:
                keys = selection["keys"]
                if not set(keys).issubset(approved[selection["name"]]):
                    raise ValidationError("Select only Secret keys listed by an administrator for this project.")
            for key in keys:
                if is_shiny and key.startswith("SHINYPROXY_"):
                    raise ValidationError("Names beginning with SHINYPROXY_ are reserved for ShinyProxy.")
                if key in selected_names:
                    raise ValidationError("Selected Secret keys must have unique variable names.")
                selected_names.add(key)
    return selected_names


def validate_environment_name_collisions(value, secret_names):
    if set(value) & secret_names:
        raise ValidationError("Configuration and Secret keys must have unique variable names.")


def validate_project_environment(value, project_id, *, is_shiny=False, secret_imports=None):
    """Validate configuration and approved Secret imports before deployment."""
    validate_environment_configuration(value, is_shiny=is_shiny)
    imports = [] if secret_imports is None else secret_imports
    secret_names = validate_project_secret_imports(imports, project_id, is_shiny=is_shiny)
    validate_environment_name_collisions(value, secret_names)


def environment_to_kubernetes(value, secret_imports=None):
    """Build deterministic Helm values for configuration and Secret imports."""
    secret_imports = [] if secret_imports is None else secret_imports
    validate_environment_variables(value)
    validate_environment_secret_imports(secret_imports)
    env = [{"name": name, "value": source["value"]} for name, source in sorted(value.items())]
    env_from = []
    for selection in sorted(secret_imports, key=lambda item: item["name"]):
        if selection.get("all") is True:
            env_from.append({"secretRef": {"name": selection["name"]}})
        else:
            env.extend(
                {"name": key, "valueFrom": {"secretKeyRef": {"name": selection["name"], "key": key}}}
                for key in sorted(selection["keys"])
            )
    return {"extraEnv": env, "extraEnvFrom": env_from}


def validate_environment_overrides(value, overrides, secret_imports=()):
    if not isinstance(overrides, dict):
        return
    if (value or any("keys" in selection for selection in secret_imports)) and "extraEnv" in overrides:
        raise ValidationError("Remove extraEnv from Kubernetes overrides before configuring environment variables.")
    if any(selection.get("all") is True for selection in secret_imports) and "extraEnvFrom" in overrides:
        raise ValidationError("Remove extraEnvFrom from Kubernetes overrides before importing Secrets.")
