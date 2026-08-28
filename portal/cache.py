from django.conf import settings
from django.core.cache import cache

PUBLIC_APPS_CACHE_KEYS = (
    "portal_public_apps:content_stats",
    "portal_public_apps:serve_category_apps",
    "portal_public_apps:page_context",
    "portal_public_apps:recent",
)

EVENTS_CACHE_KEY = "portal_events:page_data"
NEWS_CACHE_KEY = "portal_news:page_data"
COLLECTIONS_CACHE_KEY = "portal_collections:index"
HOME_CACHE_KEY = "portal_home:content_blocks"


def get_public_pages_cache_timeout() -> int:
    return getattr(settings, "PUBLIC_PAGES_CACHE_TIMEOUT", 600)


def invalidate_public_apps_cache() -> None:
    cache.delete_many(PUBLIC_APPS_CACHE_KEYS)


def invalidate_events_cache() -> None:
    cache.delete_many([EVENTS_CACHE_KEY, HOME_CACHE_KEY])


def invalidate_news_cache() -> None:
    cache.delete_many([NEWS_CACHE_KEY, HOME_CACHE_KEY])


def invalidate_collections_cache() -> None:
    cache.delete_many([COLLECTIONS_CACHE_KEY, HOME_CACHE_KEY])
