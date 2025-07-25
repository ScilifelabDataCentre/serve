import requests
from django import template
from django.conf import settings
from django.db.models.functions import Length

from studio.utils import get_logger

logger = get_logger(__name__)

register = template.Library()


@register.filter(name="split")
def split(value, arg):
    return value.all().order_by(Length("name").desc())


@register.filter
def sort_by(queryset, order):
    return queryset.order_by(order)


@register.filter(name="exists")
def exists(value, arg):
    if str(arg) in value:
        return True
    return False


@register.filter(name="count_str")
def count_str(value):
    total_length = 0
    num_tags = 0
    final_length = 42
    for tag in value:
        total_length += len(str(tag))
        if total_length > final_length:
            break
        # final_length = final_length-8
        num_tags += 1
    if num_tags == 0:
        num_tags = 1
    logger.info("LIMITS: %s %s", num_tags, total_length)
    return num_tags


@register.filter(name="subtract")
def subtract(value, arg):
    return value - arg


@register.filter(name="university_name")
def university_name(value):
    r = requests.get(settings.STUDIO_URL + "/openapi/v1/lookups/universities", params={"code": value})
    return r.json().get("data").get("name")
