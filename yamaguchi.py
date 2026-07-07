"""山口コントローラ側。

このモジュールは、「mecanum.py」と同じ全体的な構成になっています：

- 「lib.controller_state」をポーリングする
- 8バイトのUARTペイロードを構築する
- 「afs_send」で送信する

このロボットの場合、最初の4バイトは次のように使用されます：

1. Cytron 01 PWM
2. Cytron 01 DIR
3. Cytron 02 PWM
4. Cytron 02 DIR

残りの4バイトは、要求されたデフォルトの
``payload = [1] * 8`` に合わせるため、当面は「1」のままにしておきます。

ボタンのマッピングは、既存の送信側パケット形式に基づいています：

- 上    -> Cytron 01 前進
- 下  -> Cytron 01 後退
- 左  -> Cytron 02 前進
- 右  -> Cytron 02 後退

サーボボタンは、現時点では無視されます。

"""

from __future__ import annotations

import os
import time
from typing import List, Tuple

from lib.afs_uart import afs_send
from lib import controller_state


UART_DEVICE = os.environ.get("YAMAGUCHI_UART_DEVICE", "/dev/ttyAMA1")


def _u8(value: int) -> int:
    # 値を0-255のバイト範囲にクリップ（PWMやDIR値が有効な範囲に収まるようにする）
    return max(0, min(255, int(value)))


def _get_values() -> List[int]:
    vals = controller_state.get_values()
    return list(vals) if vals else []


def _button_pressed(value: int, mask: int) -> bool:
    # ビット演算でマスク位置のビットが立っているかチェック（ボタンが押されているか判定）
    return (int(value) & mask) != 0

# モーターの回転方向（PWM信号値として255=前進, 0=後退）
DIR_FORWARD = 255
DIR_REVERSE = 0


def _motor_from_buttons(forward: bool, reverse: bool) -> Tuple[int, int]:
    """モーター1つの(pwm, dir)を返す。

    方向エンコーディングはシンプルに保つ:
    - 255: 前進
    - 0: 後退
    """
    if forward:
        return 255, DIR_FORWARD
    if reverse:
        return 255, DIR_REVERSE
    return 0, 0


def _build_payload_from_controller(vals: List[int]) -> List[int]:
    """controller_state値を8バイトのUARTペイロードに変換する。

    既存の送信側フォーマットは以下を使用します:
    - vals[1] ビット 3: 上
    - vals[1] ビット 4: 下
    - vals[1] ビット 5: 左
    - vals[1] ビット 6: 右
    """
    # デフォルトペイロード：最初の4バイトはモーター制御、残り4バイトはダミー値
    payload = [1] * 8

    # vals[1]はコントローラーのボタン状態を示すバイト
    button_bytes = vals[1] if len(vals) > 1 else 0
    # 各ボタン状態をビットマスクで抽出（ビット3,4,5,6が上下左右に対応）
    up = _button_pressed(button_bytes, 0b00001000)    # ビット3: 上ボタン
    down = _button_pressed(button_bytes, 0b00010000)   # ビット4: 下ボタン
    left = _button_pressed(button_bytes, 0b00100000)   # ビット5: 左ボタン
    right = _button_pressed(button_bytes, 0b01000000)  # ビット6: 右ボタン

    # モーター1（上下ボタン）とモーター2（左右ボタン）の制御値を計算
    m1_pwm, m1_dir = _motor_from_buttons(up, down)
    m2_pwm, m2_dir = _motor_from_buttons(left, right)

    # ペイロードに値を設定（最初の4バイトがモーター制御）
    payload[0] = _u8(m1_pwm)      # Cytron 01 PWM
    payload[1] = _u8(m1_dir)      # Cytron 01 DIR（方向）
    payload[2] = _u8(m2_pwm)      # Cytron 02 PWM
    payload[3] = _u8(m2_dir)      # Cytron 02 DIR（方向）
    return payload


def run_yamaguchi(poll_interval: float = 0.02):
    """コントローラー入力をポーリングして、Cytronコマンドペイロードをシリアル経由で送信する。"""
    last_sent = None
    print("[UART INIT] Yamaguchi uses", UART_DEVICE)

    try:
        while True:
            vals = _get_values()
            # コントローラー入力がない場合はアイドル状態のペイロード（全て1）を使用
            if not vals:
                payload = [1] * 8
            else:
                payload = _build_payload_from_controller(vals)

            # ペイロードが前回と異なる場合のみ送信（無駄な送信を避ける）
            if payload != last_sent:
                if payload == [1] * 8:
                    print("[UART SEND] idle payload:", payload)
                else:
                    print("[UART SEND] cytron payload:", payload)
                # 次の比較用にペイロードのコピーを保存（リスト参照を避けるため）
                last_sent = list(payload)

            try:
                afs_send(UART_DEVICE, payload)
                print("[UART SEND] afs_send OK ->", UART_DEVICE)
            except Exception as e:
                print("[UART SEND] afs_send failed ->", UART_DEVICE, repr(e))

            time.sleep(poll_interval)
    except KeyboardInterrupt:
        pass


# 互換性のため、古いエントリーポイント名も使用可能にする
run_receiver = run_yamaguchi


if __name__ == "__main__":
    run_yamaguchi()
