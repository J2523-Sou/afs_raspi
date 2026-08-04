"""Zoukin Souten controller side.

Poll controller_state, build an 8-byte UART payload, and send it with afs_send.

Payload layout:
1. Sitechiron 01 PWM
2. Sitechiron 01 DIR
3. Sitechiron 02 PWM
4. Sitechiron 02 DIR
5. Servo power placeholder
6. Servo A/B position
7. Reserved
8. Reserved
"""

from __future__ import annotations

import os
import time
from typing import List, Tuple

from lib.afs_uart import afs_send
from lib import controller_state


UART_DEVICE = os.environ.get("ZOUKIN_SOUTEN_UART_DEVICE", "/dev/ttyAMA1")

# サーボ用の定数
# A地点/B地点の位置を変えたいときはここだけ直す
SERVO_POWER_PWM = 255
SERVO_A_ANGLE = 5
SERVO_B_ANGLE = 100


def _u8(value: int) -> int:
    return max(0, min(255, int(value)))


def _get_values() -> List[int]:
    vals = controller_state.get_values()
    return list(vals) if vals else []


def _button_pressed(value: int, mask: int) -> bool:
    return (int(value) & mask) != 0


def _circle_pressed(vals: List[int]) -> bool:
    return _button_pressed(vals[0] if len(vals) > 0 else 0, 0b00000010)


def _motor_from_buttons(forward: bool, reverse: bool) -> Tuple[int, int]:
    if forward:
        return 255, 255
    if reverse:
        return 255, 0
    return 0, 0


def _build_payload_from_controller(vals: List[int], servo_at_a: bool) -> List[int]:
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

    payload[4] = SERVO_POWER_PWM
    payload[5] = SERVO_A_ANGLE if servo_at_a else SERVO_B_ANGLE

    return payload


def run_zoukin_souten(poll_interval: float = 0.02):
    servo_at_a = True
    last_circle = False
    last_sent = None

    print("[UART INIT] Zoukin Souten uses", UART_DEVICE)

    try:
        while True:
            vals = _get_values()

            circle_now = _circle_pressed(vals)
            if circle_now and not last_circle:
                servo_at_a = not servo_at_a
                print("[SERVO] toggle:", "A地点" if servo_at_a else "B地点")
            last_circle = circle_now

            payload = _build_payload_from_controller(vals, servo_at_a)

            if payload != last_sent:
                print("[UART SEND] payload:", payload)
                last_sent = list(payload)

            try:
                afs_send(UART_DEVICE, payload)
                # print("[UART SEND] afs_send OK ->", UART_DEVICE)
            except Exception as e:
                print("[UART SEND] afs_send failed ->", UART_DEVICE, repr(e))

            time.sleep(poll_interval)
    except KeyboardInterrupt:
        pass


run_receiver = run_zoukin_souten


if __name__ == "__main__":
    run_zoukin_souten()
