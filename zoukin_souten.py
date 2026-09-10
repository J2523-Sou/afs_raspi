# 雑巾装填
# UART1

"""Zoukin Souten controller side.

Poll controller_state, build an 8-byte UART payload, and send it with afs_send.

Payload layout:
1. Sitechiron 01 forward PWM
2. Sitechiron 01 reverse PWM
3. Sitechiron 02 forward PWM
4. Sitechiron 02 reverse PWM
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
import RPi.GPIO as GPIO




UART_DEVICE = os.environ.get("ZOUKIN_SOUTEN_UART_DEVICE", "/dev/ttyAMA1")


# ===== サーボ設定：ここだけ変更すれば調整できます =====
# BCM番号（物理ピン番号ではありません）
SERVO1_PIN = 18
SERVO2_PIN = 19

# 開く・閉じる位置の角度（-90〜+90）
# サーボごとに回転方向が異なる場合は、それぞれの角度を逆に設定してください。
SERVO1_OPEN_ANGLE = 35
SERVO1_CLOSED_ANGLE = 0
SERVO2_OPEN_ANGLE = 35
SERVO2_CLOSED_ANGLE = 0

# プログラムを起動した時点の実際の状態に合わせます。
# Falseなら、最初の丸ボタンで「開く」動作になります。
START_OPEN = False

# SG90のPWM設定。通常は変更不要です。
ANGLE_RANGE = 180
TIME_RANGE = 1.9
MIN_TIME = 0.5
CYCLE_TIME = 20.0
CIRCLE_BUTTON_BYTE_INDEX = 0
CIRCLE_BUTTON_MASK = 0b00000010





def _u8(value: int) -> int:
    return max(0, min(255, int(value)))


def _get_values() -> List[int]:
    if controller_state.is_emergency_stopped():
        return []
    vals = controller_state.get_values()
    return list(vals) if vals else []


def _button_pressed(value: int, mask: int) -> bool:
    return (int(value) & mask) != 0


def _circle_pressed(values: List[int]) -> bool:
    if len(values) <= CIRCLE_BUTTON_BYTE_INDEX:
        return False
    return _button_pressed(
        values[CIRCLE_BUTTON_BYTE_INDEX], CIRCLE_BUTTON_MASK
    )


def _motor_from_buttons(forward: bool, reverse: bool) -> Tuple[int, int]:
    """メカナムドライバと同じ正転PWM・逆転PWMのペアを返す。"""
    if forward:
        return 255, 0
    if reverse:
        return 0, 255
    return 0, 0


def _build_payload_from_controller(vals: List[int]) -> List[int]:
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

    # UART経由のサーボ制御は使わない
    payload[4] = 0
    payload[5] = 0

    return payload


def move_servo(pwm, angle: float) -> bool:
    """Move the servo to an angle from -90 to +90 degrees."""
    if angle < -90 or angle > 90:
        return False

    percent = (angle + 90) / ANGLE_RANGE
    pulse_time = MIN_TIME + (TIME_RANGE * percent)
    duty_cycle = (pulse_time / CYCLE_TIME) * 100
    pwm.ChangeDutyCycle(duty_cycle)
    return True


def set_servo_open_state(pwm1, pwm2, is_open: bool) -> None:
    """Set both servos to their configured open or closed position."""
    if is_open:
        servo1_angle = SERVO1_OPEN_ANGLE
        servo2_angle = SERVO2_OPEN_ANGLE
        state_name = "OPEN"
    else:
        servo1_angle = SERVO1_CLOSED_ANGLE
        servo2_angle = SERVO2_CLOSED_ANGLE
        state_name = "CLOSED"

    if not move_servo(pwm1, servo1_angle):
        raise ValueError("SERVO1 angle must be between -90 and +90")
    if not move_servo(pwm2, servo2_angle):
        raise ValueError("SERVO2 angle must be between -90 and +90")

    print(
        "[SERVO]",
        state_name,
        "servo1=", servo1_angle,
        "servo2=", servo2_angle,
    )


def run_zoukin_souten(poll_interval: float = 0.02):
    last_sent = None
    last_circle_pressed = False
    servo_is_open = START_OPEN

    print("[UART INIT] Zoukin Souten uses", UART_DEVICE)
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(SERVO1_PIN, GPIO.OUT)
    GPIO.setup(SERVO2_PIN, GPIO.OUT)
    pwm1 = GPIO.PWM(SERVO1_PIN, 50)
    pwm2 = GPIO.PWM(SERVO2_PIN, 50)
    pwm1.start(0)
    pwm2.start(0)

    try:
        while True:
            vals = _get_values()

            circle_pressed = _circle_pressed(vals)
            if circle_pressed and not last_circle_pressed:
                servo_is_open = not servo_is_open
                set_servo_open_state(pwm1, pwm2, servo_is_open)
            last_circle_pressed = circle_pressed

            payload = _build_payload_from_controller(vals)

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
    finally:
        pwm1.stop()
        pwm2.stop()
        GPIO.cleanup(SERVO1_PIN)
        GPIO.cleanup(SERVO2_PIN)


run_receiver = run_zoukin_souten


if __name__ == "__main__":
    run_zoukin_souten()

