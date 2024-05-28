from django import template

from apps.constants import APP_REGISTRY

register = template.Library()


# settings value
@register.simple_tag
def can_create_app(user, project, app):
    app_slug = app if isinstance(app, str) else app.slug

    model_class = APP_REGISTRY.get_orm_model(app_slug)
    user_can_create = model_class.objects.user_can_create(user=user, project=project, app_slug=app_slug)

    return user_can_create
