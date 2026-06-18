import hashlib

from django.core.cache import cache

_CACHE_MISS = object()


def _cache_digest(*parts: object) -> str:
    key_parts = "|".join(str(part) for part in parts)
    return hashlib.sha256(key_parts.encode("utf-8")).hexdigest()


def build_cache_key(namespace: str, *parts: object) -> str:
    return f"{namespace}:{_cache_digest(*parts)}"


def get_cached_value(cache_key: str | None) -> object:
    if cache_key is None:
        return _CACHE_MISS

    return cache.get(cache_key, _CACHE_MISS)


def is_cache_miss(value: object) -> bool:
    return value is _CACHE_MISS


def set_cached_value(cache_key: str | None, value: object, timeout: int) -> None:
    if cache_key is not None and timeout > 0:
        cache.set(cache_key, value, timeout=timeout)


def invalidate_cache_key(cache_key: str | None) -> None:
    if cache_key is not None:
        cache.delete(cache_key)
