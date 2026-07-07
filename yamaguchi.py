"""Yamaguchi controller side.

This module follows the same overall shape as ``mecanum.py``:

- poll ``lib.controller_state``
- build an 8-byte UART payload
- send it with ``afs_send``

For this robot, the first four bytes are used like this:

1. Sitechiron 01 PWM
2. Sitechiron 01 DIR
3. Sitechiron 02 PWM
4. Sitechiron 02 DIR

The remaining 4 bytes are kept as ``1`` for now, matching the requested
``payload = [1] * 8`` default.

Button mapping comes from the existing sender-side packet format:

- Up    -> Sitechiron 01 forward
- Down  -> Sitechiron 01 reverse
- Left  -> Sitechiron 02 forward
- Right -> Sitechiron 02 reverse

Servo buttons are ignored for now.
"""

from __future__ import annotations

import os
import time
from typing import List, Tuple

from lib.afs_uart import afs_send
from lib import controller_state


UART_DEVICE = os.environ.get("YAMAGUCHI_UART_DEVICE", "/dev/ttyAMA1")


def _u8(value: int) -> int:
    return max(0, min(255, int(value)))


def _get_values() -> List[int]:
    vals = controller_state.get_values()
    return list(vals) if vals else []


def _button_pressed(value: int, mask: int) -> bool:
    return (int(value) & mask) != 0


def _motor_from_buttons(forward: bool, reverse: bool) -> Tuple[int, int]:
    """Return (pwm, dir) for one motor.

    Direction encoding is kept simple:
    - 255: forward
    - 0: reverse
    """
    if forward:
        return 255, 255
    if reverse:
        return 255, 0
    return 0, 0


def _build_payload_from_controller(vals: List[int]) -> List[int]:
    """Convert controller_state values to the 8-byte UART payload.

    The existing sender format uses:
    - vals[1] bit 3: Up
    - vals[1] bit 4: Down
    - vals[1] bit 5: Left
    - vals[1] bit 6: Right
    """
    payload = [1] * 8

    button_bytes = vals[1] if len(vals) > 1 else 0
    up = _button_pressed(button_bytes, 0b00001000)
    down = _button_pressed(button_bytes, 0b00010000)
    left = _button_pressed(button_bytes, 0b00100000)
    right = _button_pressed(button_bytes, 0b01000000)

    m1_pwm, m1_dir = _motor_from_buttons(up, down)
    m2_pwm, m2_dir = _motor_from_buttons(left, right)

    payload[0] = _u8(m1_pwm)
    payload[1] = _u8(m1_dir)
    payload[2] = _u8(m2_pwm)
    payload[3] = _u8(m2_dir)
    return payload


def run_yamaguchi(poll_interval: float = 0.02):
    """Poll controller input and send the Cytron command payload via UART."""
    last_sent = None
    print("[UART INIT] Yamaguchi uses", UART_DEVICE)

    try:
        while True:
            vals = _get_values()
            if not vals:
                payload = [1] * 8
            else:
                payload = _build_payload_from_controller(vals)

            if payload != last_sent:
                if payload == [1] * 8:
                    print("[UART SEND] idle payload:", payload)
                else:
                    print("[UART SEND] cytron payload:", payload)
                last_sent = list(payload)

            try:
                afs_send(UART_DEVICE, payload)
                print("[UART SEND] afs_send OK ->", UART_DEVICE)
            except Exception as e:
                print("[UART SEND] afs_send failed ->", UART_DEVICE, repr(e))

            time.sleep(poll_interval)
    except KeyboardInterrupt:
        pass


# Keep the old entry-point name available for compatibility.
run_receiver = run_yamaguchi


if __name__ == "__main__":
    run_yamaguchi()
