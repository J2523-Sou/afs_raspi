import pytest

from controller_receive import _recv_exact
from lib import controller_state
from lib.afs_uart import _normalize_payload, _resolve_uart_device


class ChunkedConnection:
    """recv()がデータを分割して返す接続のテストダブル。"""

    def __init__(self, *chunks):
        self._chunks = list(chunks)

    def recv(self, size):
        if not self._chunks:
            return b""
        chunk = self._chunks.pop(0)
        return chunk[:size]


@pytest.fixture(autouse=True)
def reset_controller_state():
    controller_state.clear_values()
    while controller_state.is_emergency_stopped():
        controller_state.toggle_emergency_stop()
    yield
    controller_state.clear_values()
    while controller_state.is_emergency_stopped():
        controller_state.toggle_emergency_stop()


def test_controller_state_returns_a_copy():
    controller_state.set_values([1, 2, 3])

    received = controller_state.get_values()
    received[0] = 99

    assert controller_state.get_values() == [1, 2, 3]


def test_controller_state_expires_after_max_age():
    controller_state.set_values([1, 2, 3])

    assert controller_state.get_values(max_age=1.0) == [1, 2, 3]
    assert controller_state.get_values(max_age=0.0) == []


def test_clear_controller_state_removes_stale_input():
    controller_state.set_values([1, 2, 3])
    controller_state.clear_values()

    assert controller_state.get_values() == []


def test_emergency_stop_is_a_toggle():
    assert controller_state.is_emergency_stopped() is False
    assert controller_state.toggle_emergency_stop() is True
    assert controller_state.is_emergency_stopped() is True
    assert controller_state.toggle_emergency_stop() is False


def test_recv_exact_reassembles_fragmented_data():
    connection = ChunkedConnection(b"ab", b"c", b"def")

    assert _recv_exact(connection, 6) == b"abcdef"


def test_recv_exact_returns_none_when_connection_closes_early():
    connection = ChunkedConnection(b"abc", b"")

    assert _recv_exact(connection, 4) is None


def test_uart_device_numbers_are_resolved_consistently():
    assert _resolve_uart_device(0) == "/dev/ttyAMA0"
    assert _resolve_uart_device("2") == "/dev/ttyAMA2"
    assert _resolve_uart_device("/tmp/virtual-uart") == "/tmp/virtual-uart"


def test_uart_payload_is_normalized_to_eight_bytes():
    payload = _normalize_payload([0, 1, "2", 3, 4, 5, 6, 255])

    assert payload == [0, 1, 2, 3, 4, 5, 6, 255]
    assert all(isinstance(value, int) for value in payload)


@pytest.mark.parametrize(
    "payload",
    [
        [0] * 7,
        [0] * 9,
        [-1] + [0] * 7,
        [0] * 7 + [256],
    ],
)
def test_uart_payload_rejects_invalid_shape_or_byte(payload):
    with pytest.raises(ValueError):
        _normalize_payload(payload)
