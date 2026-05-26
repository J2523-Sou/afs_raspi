"""Mecanum helper module

提供する関数:
- `axis_from_byte(b, invert_y=False)` : バイト -> -1..1
- `compute_wheel_speeds(lx, ly, rx)` : メカナムの4輪速度 (-1..1)
- `speeds_to_pwm_payload(fl, fr, rl, rr, dead=0.12)` : 4輪速度 -> 8バイト PWM ペイロード
- `run_mecanum(poll_interval=0.02)` : `controller_state` をポーリングして UART 送信
"""

from typing import List, Tuple
import time

from lib.afs_uart import afs_send
from lib import controller_state


def axis_from_byte(b, invert_y: bool = False) -> float:
    """Convert unsigned 0..255 byte to -1.0..1.0 axis.

    - X 方向: 左が 0、右が 255 -> -1..1
    - Y 方向: 上が 0、下が 255 -> 上方向を +1 にしたければ invert_y=True
    中央(128) -> 0.0
    """
    try:
        bi = int(b)
    except Exception:
        return 0.0
    if invert_y:
        val = (128 - bi) / 127.0
    else:
        val = (bi - 128) / 127.0
    return max(-1.0, min(1.0, val))


def compute_wheel_speeds(lx: float, ly: float, rx: float) -> Tuple[float, float, float, float]:
    """Compute mecanum wheel speeds from axes.

    Inputs are in -1..1 range. Returns (fl, fr, rl, rr) each in -1..1, normalized.
    Formula: fl = ly + lx + rx, fr = ly - lx - rx, rl = ly - lx + rx, rr = ly + lx - rx
    """
    fl = ly + lx + rx
    fr = ly - lx - rx
    rl = ly - lx + rx
    rr = ly + lx - rx

    m = max(abs(fl), abs(fr), abs(rl), abs(rr), 1.0)
    return fl / m, fr / m, rl / m, rr / m


def _speed_to_pwm_pair(s: float, dead: float = 0.12) -> Tuple[int, int]:
    """Convert -1.0..1.0 speed to (forward_pwm, reverse_pwm) 0..255.

    - positive s -> forward active
    - negative s -> reverse active
    - abs(s) < dead -> (0,0)
    """
    v = max(-1.0, min(1.0, s))
    if abs(v) < dead:
        return 0, 0
    pwm = int(round(abs(v) * 255))
    return (pwm, 0) if v > 0 else (0, pwm)


def speeds_to_pwm_payload(fl: float, fr: float, rl: float, rr: float, dead: float = 0.12) -> List[int]:
    """Build 8-byte payload (forward,reverse pairs) from four wheel speeds."""
    fl_f, fl_r = _speed_to_pwm_pair(fl, dead)
    fr_f, fr_r = _speed_to_pwm_pair(fr, dead)
    rl_f, rl_r = _speed_to_pwm_pair(rl, dead)
    rr_f, rr_r = _speed_to_pwm_pair(rr, dead)
    return [fl_f, fl_r, fr_f, fr_r, rl_f, rl_r, rr_f, rr_r]


def run_mecanum(poll_interval: float = 0.02):
    """Poll `controller_state.get_values()` and send mecanum motor PWM payloads.

    Expects `controller_state.get_values()` to return a list-like where
    indices 0..3 are LeftX, LeftY, RightX, RightY (0..255, origin top-left).
    """
    last = None
    last_sent = None
    try:
        while True:
            vals = controller_state.get_values()
            if vals and vals != last:
                last = list(vals)
                # 受信フォーマットに応じてマッピング
                # - WiFi/receiver が 7 バイト送る場合: Data4..Data7 に LX,LY,RX,RY が入る
                # - シンプルな配列の場合は先頭から LX,LY,RX,RY を読む
                if len(vals) >= 7:
                    lx = axis_from_byte(vals[3])
                    ly = axis_from_byte(vals[4], invert_y=True)
                    rx = axis_from_byte(vals[5])
                    ry = axis_from_byte(vals[6], invert_y=True)
                else:
                    lx = axis_from_byte(vals[0]) if len(vals) > 0 else 0.0
                    ly = axis_from_byte(vals[1], invert_y=True) if len(vals) > 1 else 0.0
                    rx = axis_from_byte(vals[2]) if len(vals) > 2 else 0.0
                    ry = axis_from_byte(vals[3], invert_y=True) if len(vals) > 3 else 0.0

                fl, fr, rl, rr = compute_wheel_speeds(lx, ly, rx)
                payload = speeds_to_pwm_payload(fl, fr, rl, rr)

                # もし全輪の絶対値がデッドゾーン未満ならペイロードを全ゼロにする
                dead = 0.12
                if max(abs(fl), abs(fr), abs(rl), abs(rr)) < dead:
                    payload = [0] * 8

                # 変更がなければ送信をスキップ
                if payload == last_sent:
                    print("[UART SEND] payload unchanged — skipping send")
                    pass
                else:
                    # 全ゼロなら停止指示として送信（必ず送る）
                    if all(p == 0 for p in payload):
                        print("[UART SEND] sending all zeros to stop motors")
                    else:
                        print("[AXIS] lx=%.3f ly=%.3f rx=%.3f ry=%.3f" % (lx, ly, rx, ry))
                        print("[MOTORS] fl=%.3f fr=%.3f rl=%.3f rr=%.3f" % (fl, fr, rl, rr))
                        print("[UART SEND] mecanum payload:", payload)

                    try:
                        afs_send(0, payload)
                        last_sent = list(payload)
                        print("[UART SEND] afs_send OK")
                    except Exception as e:
                        print("[UART SEND] afs_send failed:", repr(e))
            time.sleep(poll_interval)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    run_mecanum()