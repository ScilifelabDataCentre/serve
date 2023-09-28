"""This module contains custom tags that expose version information about the deployed system."""

from django import template

from studio.system_version import SystemVersion

register = template.Library()


@register.simple_tag
def get_version_text():
    """Gets the deployed system version as a formatted text."""
    return SystemVersion().get_version_text()


@register.simple_tag
def get_image_tag():
    """Gets the deployed system image tag."""
    return SystemVersion().get_imagetag()
