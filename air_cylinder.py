"""Air cylinder controller.

L / R ボタンのどちらかが押された瞬間にシリンダーの状態を切り替え、
SOL1 / SOL2 を相互排他的に駆動する。
"""

from __future__ import annotations

import os
import time
from typing import List, Optional

from lib.afs_uart import afs_send
from lib import controller_state


# 基板のUART端子へ接続している、追加前と同じ ttyAMA0 を既定値にする。
# 配線先を変えた場合は環境変数 AIR_CYLINDER_UART_DEVICE で変更できる。
UART_DEVICE = os.environ.get("AIR_CYLINDER_UART_DEVICE", "/dev/ttyAMA0")

# controller_state の0番目のバイトに入る L / R ボタンを使用する。
BUTTON_BYTE_INDEX = int(os.environ.get("AIR_CYLINDER_BUTTON_BYTE_INDEX", "0"))
BUTTON_MASK_L = int(os.environ.get("AIR_CYLINDER_BUTTON_MASK_L", "16"), 0)
BUTTON_MASK_R = int(os.environ.get("AIR_CYLINDER_BUTTON_MASK_R", "32"), 0)

SOLENOID_OUTPUT_INDEX = 0
OUTPUT_ON = 255
OUTPUT_OFF = 0
ERROR_RETRY_INTERVAL = 1.0


def _get_pressed_buttons() -> Optional[int]:
    """現在押されている L / R のビットを返す。入力なしの場合は None。"""
    values = controller_state.get_values()
    if not values or len(values) <= BUTTON_BYTE_INDEX:
        return None

    button_byte = int(values[BUTTON_BYTE_INDEX])
    return button_byte & (BUTTON_MASK_L | BUTTON_MASK_R)


def _build_payload(is_extended: bool) -> List[int]:
    """基板の相補回路を駆動する8バイトのAFSペイロードを作る。"""
    payload = [3] * 8

    # PICから出るSOL1だけを切り替える。SOL2は基板上の相補回路により、
    # SOL1がHIGHならLOW、SOL1がLOWならHIGHになる。
    payload[SOLENOID_OUTPUT_INDEX] = OUTPUT_ON if is_extended else OUTPUT_OFF

    return payload


def run_air_cylinder(poll_interval: float = 0.02):
    print("[UART INIT] Air cylinder uses", UART_DEVICE)
    print(
        "[BUTTON] byte_index=%d L=0x%02X R=0x%02X"
        % (BUTTON_BYTE_INDEX, BUTTON_MASK_L, BUTTON_MASK_R)
    )

    is_extended = False
    last_buttons = 0
    input_available = False
    last_logged_payload = None

    try:
        while True:
            pressed_buttons = _get_pressed_buttons()

            if pressed_buttons is None:
                # コントローラー切断時は安全側（SOL2）へ戻す。
                if is_extended:
                    print("[FAILSAFE] controller input unavailable -> RETRACTED")
                    is_extended = False
                last_buttons = 0
                input_available = False
            elif not input_available:
                # 再接続時にボタンが押されたままでも誤作動させない。
                # 一度ボタンを離してからの新しい押下のみ受け付ける。
                last_buttons = pressed_buttons
                input_available = True
            else:
                newly_pressed = pressed_buttons & ~last_buttons
                if newly_pressed:
                    is_extended = not is_extended
                    print(
                        "[BUTTON] L/R pressed ->",
                        "EXTENDED" if is_extended else "RETRACTED",
                    )
                last_buttons = pressed_buttons

            payload = _build_payload(is_extended)
            try:
                # 受信基板がいつ起動しても現在状態を受け取れるよう、
                # zoukin_souten.py と同じく毎ループUART送信する。
                afs_send(UART_DEVICE, payload)
                if payload != last_logged_payload:
                    print("[UART SEND] payload:", payload)
                    last_logged_payload = list(payload)
            except Exception as exc:
                print("[UART SEND] failed ->", UART_DEVICE, repr(exc))
                time.sleep(ERROR_RETRY_INTERVAL)
                continue

            time.sleep(poll_interval)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    run_air_cylinder()
