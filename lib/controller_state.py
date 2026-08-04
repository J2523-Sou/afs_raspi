import time
from threading import Lock


_lock = Lock()
_values = []
_updated_at = None

# この時間を超えてコントローラー入力が更新されなければ無効とみなす。
DEFAULT_MAX_AGE = 0.5


def set_values(values):
    global _values, _updated_at
    with _lock:
        _values = list(values)
        _updated_at = time.monotonic()


def clear_values():
    global _values, _updated_at
    with _lock:
        _values = []
        _updated_at = None


def get_values(max_age=DEFAULT_MAX_AGE):
    with _lock:
        if _updated_at is None:
            return []
        if max_age is not None and time.monotonic() - _updated_at > max_age:
            return []
        return list(_values)
