from django import template

register = template.Library()


@register.filter(name="is_disabled")
def is_disabled(queryset):
    return queryset.filter(login_and_signup_disabled=True).exists()
