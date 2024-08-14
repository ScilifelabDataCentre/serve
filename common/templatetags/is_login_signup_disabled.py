from django import template

register = template.Library()


@register.filter(name="is_login_signup_disabled")
def is_login_signup_disabled(queryset):
    return queryset.filter(login_and_signup_disabled=True).exists()
