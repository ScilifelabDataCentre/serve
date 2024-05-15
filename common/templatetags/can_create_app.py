from django import template

from apps.constants import SLUG_MODEL_FORM_MAP
register = template.Library()


# settings value
@register.simple_tag
def can_create_app(user, project, app):
    app_slug = app if isinstance(app, str) else app.slug

    model_class = SLUG_MODEL_FORM_MAP.get(app_slug).Model
    user_can_create = model_class.objects.user_can_create(user=user, project=project, app_slug=app_slug)

    return user_can_create
