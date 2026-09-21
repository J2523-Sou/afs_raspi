import time
from threading import Lock


_lock = Lock()
_values = []
_updated_at = None
_emergency_stop = False

# この時間を超えてコントローラー入力が更新されなければ無効とみなす。
DEFAULT_MAX_AGE = 0.5
TRIGGER_BYTE_INDEX = 0
L2_MASK = 0x20
R2_MASK = 0x40


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


def get_trigger_states(values=None):
    """L2とR2の押下状態を (L2, R2) の順で返す。"""
    if values is None:
        values = get_values()
    if len(values) <= TRIGGER_BYTE_INDEX:
        return False, False

    button_byte = int(values[TRIGGER_BYTE_INDEX])
    return bool(button_byte & L2_MASK), bool(button_byte & R2_MASK)


def is_l2_pressed(values=None):
    """L2が押されているか返す。"""
    return get_trigger_states(values)[0]


def is_r2_pressed(values=None):
    """R2が押されているか返す。"""
    return get_trigger_states(values)[1]


def toggle_emergency_stop():
    global _emergency_stop
    with _lock:
        _emergency_stop = not _emergency_stop
        return _emergency_stop


def is_emergency_stopped():
    with _lock:
        return _emergency_stop
