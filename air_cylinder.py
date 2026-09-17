# エアシリンダー

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
# controller_receive.py / README.md の通信形式に合わせる。
# 古い環境変数によって受信済みのL1/R1が無視されないよう固定する。
BUTTON_BYTE_INDEX = 1
BUTTON_MASK_L1 = 0x02
BUTTON_MASK_R1 = 0x04

# PIC出力は2本のシリンダーごとに2チャンネルを使う。
# 動作中は各ペアの片方だけON、待機中は両方OFFにする。
CYLINDER_1_A_OUTPUT_INDEX = 2
CYLINDER_1_B_OUTPUT_INDEX = 3
CYLINDER_2_A_OUTPUT_INDEX = 4
CYLINDER_2_B_OUTPUT_INDEX = 5
OUTPUT_ON = 255
OUTPUT_OFF = 0
ERROR_RETRY_INTERVAL = 1.0
SEND_LOG_INTERVAL = 1.0
# 秒単位。発射側と戻し側のON時間をそれぞれ変更できる。
FIRE_TIME = 0.5
RETURN_TIME = 0.5
STOP_PAYLOAD = [0] * 8


def _get_cylinder_states(values=None) -> Optional[Tuple[bool, bool]]:
    """(R1, L1)の押下状態を返す。"""
    if values is None:
        values = controller_state.get_values()
    if not values or len(values) <= BUTTON_BYTE_INDEX:
        return None

    button_byte = int(values[BUTTON_BYTE_INDEX])
    return bool(button_byte & BUTTON_MASK_R1), bool(button_byte & BUTTON_MASK_L1)


def _get_fire_permissions() -> Tuple[bool, bool]:
    """(左側, 右側)のシリンダー発射許可を取得する。"""
    from zoukin_souten import (
        HIDARI_CYLINDER_FIRE_PARMISSION,
        MIGI_CYLINDER_FIRE_PARMISSION,
    )

    return (
        bool(HIDARI_CYLINDER_FIRE_PARMISSION),
        bool(MIGI_CYLINDER_FIRE_PARMISSION),
    )


def _build_action_payload(cylinder: int, returning: bool) -> List[int]:
    """指定したシリンダーの発射側または戻し側だけをONにする。"""
    outputs = {
        1: (CYLINDER_1_A_OUTPUT_INDEX, CYLINDER_1_B_OUTPUT_INDEX),
        2: (CYLINDER_2_A_OUTPUT_INDEX, CYLINDER_2_B_OUTPUT_INDEX),
    }
    payload = [0] * 8
    payload[outputs[cylinder][int(returning)]] = OUTPUT_ON
    return payload


def _send_for(payload: List[int], seconds: float, poll_interval: float) -> bool:
    """UARTを更新し、非常停止・入力切断を監視する。"""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        values = controller_state.get_values()
        if controller_state.is_emergency_stopped() or not values:
            return False
        afs_send(UART_DEVICE, payload)
        time.sleep(poll_interval)
    return True


def _fire_and_return(cylinder: int, poll_interval: float) -> bool:
    """履歴の順序どおり、発射→戻し→両方OFFを1回実行する。"""
    try:
        for returning, seconds in ((False, FIRE_TIME), (True, RETURN_TIME)):
            payload = _build_action_payload(cylinder, returning)
            print("[CYLINDER %d] %s %.2fs payload=%s" % (
                cylinder, "RETURN" if returning else "FIRE", seconds, payload,
            ), flush=True)
            if not _send_for(payload, seconds, poll_interval):
                return False
        return True
    finally:
        afs_send(UART_DEVICE, STOP_PAYLOAD)
        print("[UART SEND] both OFF:", STOP_PAYLOAD, flush=True)


def run_air_cylinder(poll_interval: float = 0.02):
    print("[UART INIT] Air cylinder uses", UART_DEVICE)
    print(
        "[BUTTON] byte_index=%d L=0x%02X R=0x%02X"
        % (BUTTON_BYTE_INDEX, BUTTON_MASK_L1, BUTTON_MASK_R1)
    )

    last_logged_payload = None
    last_send_log_at = None
    sent_frames = 0
    last_logged_button_bytes = None
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
            left_permission, right_permission = _get_fire_permissions()

            fire1 = left_permission and l1_pressed and not last_l1_pressed
            fire2 = right_permission and r1_pressed and not last_r1_pressed
            last_r1_pressed = r1_pressed
            last_l1_pressed = l1_pressed

            payload = STOP_PAYLOAD
            try:
                # 過去の割り当て: L1で1・2、R1で3・4。同時押しは順番に実行。
                for cylinder, requested in ((1, fire1), (2, fire2)):
                    if requested and not _fire_and_return(cylinder, poll_interval):
                        break
                # 受信基板がいつ起動しても現在状態を受け取れるよう、
                # zoukin_souten.py と同じく毎ループUART送信する。
                afs_send(UART_DEVICE, payload)
                sent_frames += 1
                now = time.monotonic()
                if (payload != last_logged_payload or last_send_log_at is None
                        or now - last_send_log_at >= SEND_LOG_INTERVAL):
                    print("[UART SEND] device=%s idle_frames=%d payload=%s"
                          % (UART_DEVICE, sent_frames, payload), flush=True)
                    last_logged_payload = list(payload)
                    last_send_log_at = now
            except Exception as exc:
                print("[UART SEND] failed ->", UART_DEVICE, repr(exc), flush=True)
                time.sleep(ERROR_RETRY_INTERVAL)
                continue

            time.sleep(poll_interval)
    except KeyboardInterrupt:
        pass


def main():
    # controller_state はプロセス内の共有メモリなので、受信も同じプロセスで行う。
    # run_all.py は受信スレッドを起動済みのため run_air_cylinder() を直接使う。
    from threading import Thread
    from controller_receive import run_receiver

    Thread(target=run_receiver, daemon=True).start()
    run_air_cylinder()


if __name__ == "__main__":
    main()
