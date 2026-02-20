import copy
import time
from collections import OrderedDict
from functools import wraps
from threading import RLock


def _freeze(value):
    if isinstance(value, (str, int, float, bool, type(None), bytes)):
        return value
    if isinstance(value, dict):
        items = []
        for key, val in value.items():
            items.append((str(key), _freeze(val)))
        items.sort(key=lambda item: item[0])
        return tuple(items)
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return tuple(sorted((_freeze(item) for item in value), key=repr))
    return repr(value)


def _make_key(args, kwargs):
    return (_freeze(args), _freeze(kwargs))


def ttl_cache(ttl_seconds=45, maxsize=2048):
    ttl = int(ttl_seconds or 0)
    limit = max(1, int(maxsize or 1))

    def decorator(func):
        cache_store = OrderedDict()
        lock = RLock()

        @wraps(func)
        def wrapper(*args, **kwargs):
            if ttl <= 0:
                return func(*args, **kwargs)

            key = _make_key(args, kwargs)
            now = time.monotonic()

            with lock:
                expired_keys = [k for k, (expires_at, _) in cache_store.items() if expires_at <= now]
                for expired_key in expired_keys:
                    cache_store.pop(expired_key, None)

                cached = cache_store.get(key)
                if cached is not None:
                    expires_at, value = cached
                    if expires_at > now:
                        cache_store.move_to_end(key)
                        return copy.deepcopy(value)
                    cache_store.pop(key, None)

            result = func(*args, **kwargs)
            result_snapshot = copy.deepcopy(result)

            with lock:
                cache_store[key] = (time.monotonic() + ttl, result_snapshot)
                cache_store.move_to_end(key)
                while len(cache_store) > limit:
                    cache_store.popitem(last=False)

            return copy.deepcopy(result_snapshot)

        def cache_clear():
            with lock:
                cache_store.clear()

        wrapper.cache_clear = cache_clear
        return wrapper

    return decorator
