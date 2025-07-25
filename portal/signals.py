import structlog
from django.dispatch import receiver
from django_structlog.signals import bind_extra_request_metadata


@receiver(bind_extra_request_metadata)
def remove_ip_address(sender, request, logger, **kwargs):
    structlog.contextvars.bind_contextvars(ip=None)
