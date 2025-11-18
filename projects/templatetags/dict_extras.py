from django import template

register = template.Library()


@register.filter
def get_item(d, key):
    if d is None:
        return None
    return d.get(key)
