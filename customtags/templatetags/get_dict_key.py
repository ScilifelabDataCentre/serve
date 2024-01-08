from django import template


register = template.Library()


@register.filter
def dict_key(dictionary, key):
    return dictionary.get(key, None)