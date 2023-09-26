from django import template

register = template.Library()


# Application version information
@register.simple_tag
def get_version():
    return "<date> (v0.0.0)"


@register.simple_tag
def get_image_tag():
    return "<tag>"
