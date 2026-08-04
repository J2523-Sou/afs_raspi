import atexit
import importlib
from threading import Lock

HOST = None
PORT = None

DEFAULT_BAUDRATE = 9600
DEFAULT_TIMEOUT = 0.1

_connections = {}
_connections_lock = Lock()
_device_locks = {}

def afs_init(ip, port):

    global HOST, PORT
    HOST = ip
    PORT = port  # 必要なら int に変換

def _resolve_uart_device(uartNo):
    if isinstance(uartNo, int):
        return f"/dev/ttyAMA{uartNo}"

    uart_text = str(uartNo)
    if uart_text.isdigit():
        return f"/dev/ttyAMA{uart_text}"
    return uart_text


def _normalize_payload(data):
    payload = list(data)
    if len(payload) != 8:
        raise ValueError("送信データ配列は8個の値が必要です")

    normalized = []
    for index, value in enumerate(payload):
        byte_value = int(value)
        if byte_value < 0 or byte_value > 255:
            raise ValueError(f"data[{index}] が 0..255 の範囲外です: {value}")
        normalized.append(byte_value)
    return normalized


def _load_serial_module():
    try:
        return importlib.import_module("serial")
    except ModuleNotFoundError as exc:
        raise RuntimeError("pyserial が必要です。pip で pyserial をインストールしてください") from exc


def _close_serial(ser):
    try:
        ser.close()
    except Exception:
        pass


def _get_device_lock(device):
    with _connections_lock:
        lock = _device_locks.get(device)
        if lock is None:
            lock = Lock()
            _device_locks[device] = lock
        return lock


def close_all():
    with _connections_lock:
        connections = [
            (device, ser, _device_locks.get(device))
            for device, ser in _connections.items()
        ]
        _connections.clear()
    for _device, ser, device_lock in connections:
        if device_lock is None:
            _close_serial(ser)
        else:
            with device_lock:
                _close_serial(ser)


atexit.register(close_all)


def afs_send(uartNo, data):
    return afs_uart(uartNo, data)


def afs_uart(uartNo, data):
    device = _resolve_uart_device(uartNo)
    payload = _normalize_payload(data)
    frame = bytes([0xAA, *payload])
    serial = _load_serial_module()

    # ポートを送信ごとに開閉せず再利用する。ポートごとのロックは、
    # 同一ポートへの複数スレッド送信によるフレーム混在を防ぐ。
    device_lock = _get_device_lock(device)
    with device_lock:
        with _connections_lock:
            ser = _connections.get(device)
        if ser is None or not getattr(ser, "is_open", True):
            ser = serial.Serial(device, DEFAULT_BAUDRATE, timeout=DEFAULT_TIMEOUT)
            with _connections_lock:
                _connections[device] = ser

        try:
            ser.write(frame)
            ser.flush()
        except Exception:
            with _connections_lock:
                if _connections.get(device) is ser:
                    _connections.pop(device, None)
            _close_serial(ser)
            raise
        
