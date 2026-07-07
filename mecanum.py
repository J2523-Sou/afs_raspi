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
    fl = ly + lx + rx
    fr = ly - lx - rx
    rl = ly - lx + rx
    rr = ly + lx - rx

    m = max(abs(fl), abs(fr), abs(rl), abs(rr), 1.0)
    return fl / m, fr / m, rl / m, rr / m


def _speed_to_pwm_pair(s: float, dead: float = 0.12) -> Tuple[int, int]:
    v = max(-1.0, min(1.0, s))
    if abs(v) < dead:
        return 0, 0
    pwm = int(round(abs(v) * 255))
    return (pwm, 0) if v > 0 else (0, pwm)


def speeds_to_pwm_payload(fl: float, fr: float, rl: float, rr: float, dead: float = 0.12) -> List[int]:
    fl_f, fl_r = _speed_to_pwm_pair(fl, dead)
    fr_f, fr_r = _speed_to_pwm_pair(fr, dead)
    rl_f, rl_r = _speed_to_pwm_pair(rl, dead)
    rr_f, rr_r = _speed_to_pwm_pair(rr, dead)
    return [fl_f, fl_r, fr_f, fr_r, rl_f, rl_r, rr_f, rr_r]


def run_mecanum(poll_interval: float = 0.02):
    """`controller_state.get_values()` をポーリングしてメカナムモーター PWM ペイロードを送信する。"""
    
    # === 【変更】ロボットの現在の内部的な状態（現在値）を保持する変数 ===
    cur_lx = 0.0
    cur_ly = 0.0
    cur_rx = 0.0
    cur_ry = 0.0

    # === 【追加】加減速の「止まるスピード」を調整するパラメータ ===
    # 0.0〜1.0 の範囲で指定します。
    # 1.0 : 一瞬で追従（元の挙動と同じ）
    # 0.1 : 毎ループ、目標値との差の10%ずつ近づく（滑らかに加減速・停止する）
    # 0.01: 非常にゆっくり時間をかけて加減速・停止する
    RESPONSE_SPEED = 0.25

    last_sent = None
    
    try:
        while True:
            vals = controller_state.get_values()
            if vals:
                # 1. コントローラーからの目標値（Target）を取得
                if len(vals) >= 7:
                    tgt_lx = axis_from_byte(vals[3])
                    tgt_ly = axis_from_byte(vals[4], invert_y=True)
                    tgt_rx = axis_from_byte(vals[5])
                    tgt_ry = axis_from_byte(vals[6], invert_y=True)
                else:
                    tgt_lx = axis_from_byte(vals[0]) if len(vals) > 0 else 0.0
                    tgt_ly = axis_from_byte(vals[1], invert_y=True) if len(vals) > 1 else 0.0
                    tgt_rx = axis_from_byte(vals[2]) if len(vals) > 2 else 0.0
                    tgt_ry = axis_from_byte(vals[3], invert_y=True) if len(vals) > 3 else 0.0

                # 2. 【重要】目標値に向けて、現在値をゆっくり近づける計算
                # (目標値 - 現在値) に割合をかけた分だけ、現在値を増減させる
                cur_lx += (tgt_lx - cur_lx) * RESPONSE_SPEED
                cur_ly += (tgt_ly - cur_ly) * RESPONSE_SPEED
                cur_rx += (tgt_rx - cur_rx) * RESPONSE_SPEED
                cur_ry += (tgt_ry - cur_ry) * RESPONSE_SPEED

                # 3. 滑らかに変化する「現在値」を使って4輪の速度を計算
                fl, fr, rl, rr = compute_wheel_speeds(cur_lx, cur_ly, cur_rx)
                payload = speeds_to_pwm_payload(fl, fr, rl, rr)

                # 全輪の絶対値がデッドゾーン未満ならペイロードを全ゼロにする
                dead = 0.12
                if max(abs(fl), abs(fr), abs(rl), abs(rr)) < dead:
                    payload = [0] * 8

                # 4. 前回の送信データと変化があれば（または停止指示なら）UART送信
                if payload != last_sent:
                    if all(p == 0 for p in payload):
                        print("[UART SEND] sending all zeros to stop motors")
                    else:
                        print("[AXIS] cur_lx=%.3f cur_ly=%.3f cur_rx=%.3f" % (cur_lx, cur_ly, cur_rx))
                        print("[MOTORS] fl=%.3f fr=%.3f rl=%.3f rr=%.3f" % (fl, fr, rl, rr))
                        print("[UART SEND] mecanum payload:", payload)

                    try:
                        afs_send(0, payload)
                        last_sent = list(payload)
                        print("[UART SEND] afs_send OK")
                    except Exception as e:
                        print("[UART SEND] afs_send failed:", repr(e))
            
            # 毎ループの周期を保つために sleep は常に実行
            time.sleep(poll_interval)
            
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    run_mecanum()