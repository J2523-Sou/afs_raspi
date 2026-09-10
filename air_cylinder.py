# エアシリンダー
# UART2

from __future__ import annotations

import os
import time
from typing import List, Optional, Tuple

from lib.afs_uart import afs_send
from lib import controller_state


# ソレノイド基板はGPIO4(TX) / GPIO5(RX)に割り当てたttyAMA2を使用する。
# 配線先を変えた場合は環境変数 AIR_CYLINDER_UART_DEVICE で変更できる。
UART_DEVICE = os.environ.get("AIR_CYLINDER_UART_DEVICE", "/dev/ttyAMA2")

# 7バイト受信形式のdata2: L1=bit1 (0x02), R1=bit2 (0x04)
BUTTON_BYTE_INDEX = int(os.environ.get("AIR_CYLINDER_BUTTON_BYTE_INDEX", "1"))
BUTTON_MASK_L1 = int(os.environ.get("AIR_CYLINDER_BUTTON_MASK_L1", "2"), 0)
BUTTON_MASK_R1 = int(os.environ.get("AIR_CYLINDER_BUTTON_MASK_R1", "4"), 0)

# PIC出力は2本のシリンダーごとに2チャンネルを使う。
# 各ペアは必ず片方だけONにする。
CYLINDER_1_A_OUTPUT_INDEX = 2
CYLINDER_1_B_OUTPUT_INDEX = 3
CYLINDER_2_A_OUTPUT_INDEX = 4
CYLINDER_2_B_OUTPUT_INDEX = 5
OUTPUT_ON = 255
OUTPUT_OFF = 0
ERROR_RETRY_INTERVAL = 1.0


def _get_cylinder_states(values=None) -> Optional[Tuple[bool, bool]]:
    """(R1, L1)の押下状態を返す。"""
    if values is None:
        values = controller_state.get_values()
    if not values or len(values) <= BUTTON_BYTE_INDEX:
        return None

    button_byte = int(values[BUTTON_BYTE_INDEX])
    return bool(button_byte & BUTTON_MASK_R1), bool(button_byte & BUTTON_MASK_L1)


def _build_payload(
    cylinder1_b_selected: bool,
    cylinder2_b_selected: bool,
) -> List[int]:
    """2組の相補出力を持つ8バイトペイロードを作る。"""
    payload = [0] * 8
    payload[CYLINDER_1_A_OUTPUT_INDEX] = (
        OUTPUT_OFF if cylinder1_b_selected else OUTPUT_ON
    )
    payload[CYLINDER_1_B_OUTPUT_INDEX] = (
        OUTPUT_ON if cylinder1_b_selected else OUTPUT_OFF
    )
    payload[CYLINDER_2_A_OUTPUT_INDEX] = (
        OUTPUT_OFF if cylinder2_b_selected else OUTPUT_ON
    )
    payload[CYLINDER_2_B_OUTPUT_INDEX] = (
        OUTPUT_ON if cylinder2_b_selected else OUTPUT_OFF
    )
    return payload


def run_air_cylinder(poll_interval: float = 0.02):
    print("[UART INIT] Air cylinder uses", UART_DEVICE)
    print(
        "[BUTTON] byte_index=%d L=0x%02X R=0x%02X"
        % (BUTTON_BYTE_INDEX, BUTTON_MASK_L1, BUTTON_MASK_R1)
    )

    last_logged_payload = None
    last_logged_button_bytes = None
    cylinder1_b_selected = False
    cylinder2_b_selected = False
    last_r1_pressed = False
    last_l1_pressed = False

    try:
        while True:
            values = controller_state.get_values()
            if values:
                button_bytes = list(values[:3])
                if button_bytes != last_logged_button_bytes:
                    print("[CONTROLLER] button bytes[0:3]:", button_bytes)
                    last_logged_button_bytes = button_bytes

            states = _get_cylinder_states(values)
            r1_pressed, l1_pressed = states if states is not None else (False, False)

            # 押した瞬間に、対応するペア内の有効チャンネルを切り替える。
            # 長押し中は現在の組み合わせを維持する。
            if r1_pressed and not last_r1_pressed:
                cylinder1_b_selected = not cylinder1_b_selected
                print(
                    "[R1] cylinder1 ->",
                    "CH2" if cylinder1_b_selected else "CH1",
                )
            if l1_pressed and not last_l1_pressed:
                cylinder2_b_selected = not cylinder2_b_selected
                print(
                    "[L1] cylinder2 ->",
                    "CH4" if cylinder2_b_selected else "CH3",
                )
            last_r1_pressed = r1_pressed
            last_l1_pressed = l1_pressed

            payload = [0] * 8 if controller_state.is_emergency_stopped() else _build_payload(
                cylinder1_b_selected,
                cylinder2_b_selected,
            )
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
