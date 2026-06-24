from django.core.cache import cache


PUBLIC_APPS_CACHE_KEYS = (
    "portal_public_apps:content_stats",
    "portal_public_apps:page_context",
    "portal_public_apps:recent",
)


def invalidate_public_apps_cache() -> None:
    cache.delete_many(PUBLIC_APPS_CACHE_KEYS)
