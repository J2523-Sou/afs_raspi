# エアシリンダー
# UART2

from __future__ import annotations

import os
import time
from typing import List

from lib.afs_uart import afs_send
from lib import controller_state
import zoukin_souten


# ソレノイド基板はGPIO4(TX) / GPIO5(RX)に割り当てたttyAMA2を使用する。
# 配線先を変えた場合は環境変数 AIR_CYLINDER_UART_DEVICE で変更できる。
UART_DEVICE = os.environ.get("AIR_CYLINDER_UART_DEVICE", "/dev/ttyAMA2")

# 7バイト受信形式のdata2: L1=bit1 (0x02), R1=bit2 (0x04)
BUTTON_BYTE_INDEX = int(os.environ.get("AIR_CYLINDER_BUTTON_BYTE_INDEX", "1"))
BUTTON_MASK_L1 = int(os.environ.get("AIR_CYLINDER_BUTTON_MASK_L1", "2"), 0)
BUTTON_MASK_R1 = int(os.environ.get("AIR_CYLINDER_BUTTON_MASK_R1", "4"), 0)

ERROR_RETRY_INTERVAL = 1.0
FIRE_PERMISSION_YES = "YES"
FIRE_TIME = 0.5
RETURN_TIME = 0.5
STOP_PAYLOAD = [0] * 8

# (物理アクション名, 逆に割り当てるコントローラーボタン, 出力チャンネル, [発射, 戻し])
# 動作を増やすときは、この配列に1行追加します。
CYLINDER_ACTIONS = [
    # コントローラーL1でR1側、R1でL1側を動かす。
    ("R1", BUTTON_MASK_L1, (2, 3), [(255, 0), (0, 255)]),
    ("L1", BUTTON_MASK_R1, (4, 5), [(255, 0), (0, 255)]),
]


def _is_pressed(values, button_mask):
    return bool(
        values
        and len(values) > BUTTON_BYTE_INDEX
        and values[BUTTON_BYTE_INDEX] & button_mask
    )


def _build_payload(selected_actions) -> List[int]:
    """選択中の送信値を、対応表から8バイトにまとめる。"""
    payload = [0] * 8
    for action_number, action in enumerate(CYLINDER_ACTIONS):
        _button, _mask, output_indexes, patterns = action
        for output_index, output_value in zip(
            output_indexes, patterns[selected_actions[action_number]]
        ):
            payload[output_index] = output_value
    return payload


def _build_action_payload(action_number: int, pattern_number: int) -> List[int]:
    """指定した1アクションだけを動かすペイロードを作る。"""
    payload = [0] * 8
    _button, _mask, output_indexes, patterns = CYLINDER_ACTIONS[action_number]
    for output_index, output_value in zip(
        output_indexes, patterns[pattern_number]
    ):
        payload[output_index] = output_value
    return payload


def _is_fire_allowed(button_name: str) -> bool:
    zoukin_souten.fire_cylinder_check()
    permissions = {
        "R1": zoukin_souten.R1_CYLINDER_FIRE_PARMISSION,
        "L1": zoukin_souten.L1_CYLINDER_FIRE_PARMISSION,
    }
    return permissions.get(button_name) == FIRE_PERMISSION_YES


def _send_for(payload: List[int], seconds: float, poll_interval: float) -> bool:
    """指定した出力を送信し、非常停止や切断時は中断する。"""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if controller_state.is_emergency_stopped() or not controller_state.get_values():
            return False
        afs_send(UART_DEVICE, payload)
        time.sleep(poll_interval)
    return True


def _fire_and_return(action_number: int, action, poll_interval: float) -> bool:
    """発射方向へ動かし、戻し方向へ動かして停止する。"""
    button_name, _button_mask, _output_indexes, _patterns = action
    if not _is_fire_allowed(button_name):
        print(f"[{button_name}] 発射許可なし")
        return False

    try:
        if not _send_for(
            _build_action_payload(action_number, 0), FIRE_TIME, poll_interval
        ):
            return False
        return _send_for(
            _build_action_payload(action_number, 1),
            RETURN_TIME,
            poll_interval,
        )
    finally:
        afs_send(UART_DEVICE, STOP_PAYLOAD)


def run_air_cylinder(poll_interval: float = 0.02):
    print("[UART INIT] Air cylinder uses", UART_DEVICE)
    print(
        "[BUTTON] byte_index=%d L=0x%02X R=0x%02X"
        % (BUTTON_BYTE_INDEX, BUTTON_MASK_L1, BUTTON_MASK_R1)
    )

    last_logged_payload = None
    last_logged_button_bytes = None
    last_pressed = [False] * len(CYLINDER_ACTIONS)

    try:
        while True:
            values = controller_state.get_values()
            if values:
                button_bytes = list(values[:3])
                if button_bytes != last_logged_button_bytes:
                    print("[CONTROLLER] button bytes[0:3]:", button_bytes)
                    last_logged_button_bytes = button_bytes

            for action_number, action in enumerate(CYLINDER_ACTIONS):
                button_name, button_mask, _outputs, patterns = action
                is_pressed = _is_pressed(values, button_mask)

                if is_pressed and not last_pressed[action_number]:
                    _fire_and_return(action_number, action, poll_interval)
                last_pressed[action_number] = is_pressed

            payload = (
                [0] * 8
                if controller_state.is_emergency_stopped()
                else STOP_PAYLOAD
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
