"""DualSenseのL2/R2でエアシリンダーを制御する単独実行プログラム。

コントローラー入力には共通の ``lib.controller_state``、
PICへの送信には共通の ``lib.afs_uart`` を使用する。

入力フレーム:
    0xAB + 9 bytes
    [buttons0, buttons1, buttons2, lx, ly, rx, ry, l2, r2]

PIC出力（0xAA + 8 bytes）:
    PWM3: シリンダー伸長（R2）
    PWM4: シリンダー収縮（L2）

既存の0xAA + 7 bytesも読み捨てず受信するが、アナログトリガー値がないため
安全側としてPWM3/PWM4を両方LOWにする。
"""

from __future__ import annotations

import threading
import time
from typing import List, Tuple

from controller_receive import run_receiver
from lib.afs_uart import afs_uart
from lib import controller_state


# 他機構とのUART割り当て:
#   UART0: メカナム
#   UART1: 山口機構
#   UART2: エアシリンダー
UART_NO = 2

TRIGGER_THRESHOLD = 0.5
L2_INDEX = 7
R2_INDEX = 8
PWM3_INDEX = 2
PWM4_INDEX = 3


def _get_values() -> List[int]:
    values = controller_state.get_values()
    return list(values) if values else []


def _trigger_value(values: List[int], index: int) -> float:
    if len(values) <= index:
        return 0.0
    return max(0, min(255, int(values[index]))) / 255.0


def cylinder_pwm_from_triggers(
    l2_value: float,
    r2_value: float,
    threshold: float = TRIGGER_THRESHOLD,
) -> Tuple[int, int]:
    """L2/R2から(PWM3, PWM4)を生成し、同時HIGHを禁止する。"""
    retract_pressed = float(l2_value) >= threshold
    extend_pressed = float(r2_value) >= threshold

    if extend_pressed == retract_pressed:
        return 0, 0
    if extend_pressed:
        return 255, 0
    return 0, 255


def build_pic_payload(values: List[int]) -> list[int]:
    """コントローラーフレームをPIC向け8バイトデータへ変換する。"""
    pwm3, pwm4 = cylinder_pwm_from_triggers(
        _trigger_value(values, L2_INDEX),
        _trigger_value(values, R2_INDEX),
    )

    payload = [0] * 8
    payload[PWM3_INDEX] = pwm3
    payload[PWM4_INDEX] = pwm4

    # 出力直前にも独立したインターロックを置く。
    if payload[PWM3_INDEX] and payload[PWM4_INDEX]:
        payload[PWM3_INDEX] = 0
        payload[PWM4_INDEX] = 0
    return payload


def send_pic_payload(payload: list[int]) -> None:
    if len(payload) != 8 or any(value < 0 or value > 255 for value in payload):
        raise ValueError("PIC送信データは0..255の8要素で指定してください")
    afs_uart(UART_NO, payload)


def run_cylinder(poll_interval: float = 0.02) -> None:
    """controller_stateを監視し、シリンダー用PICへUART出力する。"""
    print(f"[CYLINDER] PIC UART: {UART_NO}")
    last_sent = None
    try:
        while True:
            payload = build_pic_payload(_get_values())
            if payload != last_sent:
                send_pic_payload(payload)
                last_sent = list(payload)
            time.sleep(poll_interval)
    except KeyboardInterrupt:
        send_pic_payload([0] * 8)


if __name__ == "__main__":
    receiver = threading.Thread(target=run_receiver, daemon=True)
    receiver.start()
    run_cylinder()
