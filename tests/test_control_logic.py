import pytest

from controller_receive import _recv_exact
from lib import controller_state
from lib.afs_uart import _normalize_payload, _resolve_uart_device
from mecanum import compute_wheel_speeds, speeds_to_pwm_payload


@pytest.mark.parametrize(
    "axes, expected",
    [
        ((0, 1, 0), (-1, 1, 1, -1)),  # Forward -> old left.
        ((0, -1, 0), (1, -1, -1, 1)),  # Backward -> old right.
        ((1, 0, 0), (1, 1, 1, 1)),  # Right -> old forward.
        ((-1, 0, 0), (-1, -1, -1, -1)),  # Left -> old backward.
        ((0, 0, 1), (1, -1, 1, -1)),  # Rotation unchanged.
        ((0, 0, -1), (-1, 1, -1, 1)),
        ((0, 0, 0), (0, 0, 0, 0)),
        ((1, 1, 1), (1 / 3, 1 / 3, 1, -1 / 3)),
    ],
)
def test_mecanum_uses_old_left_as_front(axes, expected):
    assert compute_wheel_speeds(*axes) == pytest.approx(expected)


def test_mecanum_forward_pwm_keeps_original_wiring_order():
    assert speeds_to_pwm_payload(*compute_wheel_speeds(0, 1, 0)) == [
        0, 255, 255, 0, 255, 0, 0, 255,
    ]


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
    assert _resolve_uart_device("/dev/ttyAMA1") == "/dev/ttyAMA1"


@pytest.mark.parametrize("uart_number", [-1, 3, "3", "/tmp/virtual-uart", True])
def test_uart_device_rejects_uart_outside_zero_to_two(uart_number):
    with pytest.raises(ValueError):
        _resolve_uart_device(uart_number)


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
