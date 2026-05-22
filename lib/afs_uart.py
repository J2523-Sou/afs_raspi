import importlib

HOST = None
PORT = None

DEFAULT_BAUDRATE = 9600
DEFAULT_TIMEOUT = 0.1

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


def afs_send(uartNo, data):
    return afs_uart(uartNo, data)


def afs_uart(uartNo, data):
    device = _resolve_uart_device(uartNo)
    payload = _normalize_payload(data)
    frame = bytes([0xAA, *payload])
    serial = _load_serial_module()

    ser = serial.Serial(device, DEFAULT_BAUDRATE, timeout=DEFAULT_TIMEOUT)
    try:
        ser.write(frame)
        ser.flush()
    finally:
        ser.close()
        
