from django import template

register = template.Library()


@register.filter(name="is_login_signup_disabled")
def is_login_signup_disabled(items):
    # `items` may be None, a QuerySet, or a cached list (see common.context_processors)
    if items is None:
        return False

    return any(obj.login_and_signup_disabled for obj in items)
