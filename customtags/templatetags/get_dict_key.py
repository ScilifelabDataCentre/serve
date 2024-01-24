from django import template

register = template.Library()


@register.filter
def dict_key(dictionary, key):
    """
    Allows fetching of dictionary values where keys have whitespace in templates

    Example:
    my_dict = {"some key": "some value"}
    In the template you can not use {{ my_dict.some key }}, so with this filter you can do
    {{ my_dict|dict_key:"some key" }}
    """
    return dictionary.get(key, None)
