from threading import Lock


_lock = Lock()
_values = []


def set_values(values):
    global _values
    with _lock:
        _values = list(values)


def get_values():
    with _lock:
        return list(_values)