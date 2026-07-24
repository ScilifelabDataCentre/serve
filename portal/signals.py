import structlog
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from django_structlog.signals import bind_extra_request_metadata

from portal.cache import (
    invalidate_collections_cache,
    invalidate_events_cache,
    invalidate_news_cache,
)
from portal.models import Collection, EventsObject, NewsObject


@receiver(bind_extra_request_metadata)
def remove_ip_address(sender, request, logger, **kwargs):
    structlog.contextvars.bind_contextvars(ip=None)


@receiver([post_save, post_delete], sender=EventsObject)
def clear_events_cache(sender, **kwargs):
    invalidate_events_cache()


@receiver([post_save, post_delete], sender=NewsObject)
def clear_news_cache(sender, **kwargs):
    invalidate_news_cache()


@receiver([post_save, post_delete], sender=Collection)
def clear_collections_cache(sender, **kwargs):
    invalidate_collections_cache()
