from django.dispatch import receiver

from django_structlog.signals import bind_extra_request_metadata
import structlog


@receiver(bind_extra_request_metadata)
def remove_ip_address(request, logger, **kwargs):
    structlog.contextvars.bind_contextvars(ip=None)
