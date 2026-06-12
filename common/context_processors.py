from django.conf import settings
from django.core.cache import cache

from studio.utils import get_logger

from .models import MaintenanceMode

logger = get_logger(__name__)

MAINTENANCE_MODE_CACHE_KEY = "maintenance_mode"


def _maintenance_mode_cache_timeout() -> int:
    return getattr(settings, "MAINTENANCE_MODE_CACHE_TIMEOUT", 30)


def maintenance_mode(request):
    cache_timeout = _maintenance_mode_cache_timeout()
    if cache_timeout > 0:
        try:
            cached_data = cache.get(MAINTENANCE_MODE_CACHE_KEY)
        except Exception as e:
            logger.debug("Error fetching maintenance mode cache: %s", e)
        else:
            if cached_data is not None:
                return {"maintenance_mode": cached_data}

    try:
        data = list(MaintenanceMode.objects.all())
    except Exception as e:
        logger.debug("Error fetching maintenance mode data: %s", e)
        data = []
    else:
        if cache_timeout > 0:
            try:
                cache.set(MAINTENANCE_MODE_CACHE_KEY, data, cache_timeout)
            except Exception as e:
                logger.debug("Error setting maintenance mode cache: %s", e)

    return {"maintenance_mode": data}
