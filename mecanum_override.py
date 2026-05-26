"""Mecanum runner override

このモジュールは既存の `mecanum.py` の機能を再利用しつつ、
受信データの `axis[5] > -0.5`（右スティックX が -0.5 より大きい）
の場合に全輪へ強度128で送信する特別処理を行います。

できるだけ既存ファイルを変更せずに動作を差し替える目的で作成しています。
"""
from typing import List, Tuple
import time

from lib.afs_uart import afs_send
from lib import controller_state
import mecanum


def run_mecanum_override(poll_interval: float = 0.02):
    """controller_state をポーリングし、特別条件で全輪128を送信。

    - 受信配列が7バイト以上であれば `vals[5]` を右スティックXとして解釈。
    - `mecanum.axis_from_byte(vals[5]) > -0.5` の場合、
      強制的に `[128,0,128,0,128,0,128,0]` を送信する。
    - それ以外は既存の `mecanum` ロジックに従って速度を計算・送信する。
    """
    last = None
    last_sent = None
    try:
        while True:
            vals = controller_state.get_values()
            if not vals:
                time.sleep(poll_interval)
                continue

            # 値が変わったら再処理
            if list(vals) != last:
                last = list(vals)

            # 受信フォーマットに応じてマッピング（mecanum.py と同じ）
            if len(vals) >= 7:
                lx = mecanum.axis_from_byte(vals[3])
                ly = mecanum.axis_from_byte(vals[4], invert_y=True)
                rx = mecanum.axis_from_byte(vals[5])
                ry = mecanum.axis_from_byte(vals[6], invert_y=True)
            else:
                lx = mecanum.axis_from_byte(vals[0]) if len(vals) > 0 else 0.0
                ly = mecanum.axis_from_byte(vals[1], invert_y=True) if len(vals) > 1 else 0.0
                rx = mecanum.axis_from_byte(vals[2]) if len(vals) > 2 else 0.0
                ry = mecanum.axis_from_byte(vals[3], invert_y=True) if len(vals) > 3 else 0.0

            # 特別処理: axis[5] (右スティックX) が -0.5 より大きければ
            # 全輪に強度128で送信する
            special_condition = False
            if len(vals) >= 6:
                try:
                    special_condition = mecanum.axis_from_byte(vals[5]) > -0.5
                except Exception:
                    special_condition = False

            if special_condition:
                payload = [128, 0, 128, 0, 128, 0, 128, 0]
                print('[SPECIAL] detected axis[5] > -0.5 — sending all 128')
                try:
                    afs_send(0, payload)
                    last_sent = list(payload)
                    print('[UART SEND] special afs_send OK')
                except Exception as e:
                    print('[UART SEND] special afs_send failed:', repr(e))
            else:
                # 通常のメカナム処理
                fl, fr, rl, rr = mecanum.compute_wheel_speeds(lx, ly, rx)
                payload = mecanum.speeds_to_pwm_payload(fl, fr, rl, rr)

                dead = 0.12
                if max(abs(fl), abs(fr), abs(rl), abs(rr)) < dead:
                    payload = [0] * 8

                if payload == last_sent:
                    print('[UART SEND] payload unchanged — skipping send')
                else:
                    if all(p == 0 for p in payload):
                        print('[UART SEND] sending all zeros to stop motors')
                    else:
                        print('[AXIS] lx=%.3f ly=%.3f rx=%.3f ry=%.3f' % (lx, ly, rx, ry))
                        print('[MOTORS] fl=%.3f fr=%.3f rl=%.3f rr=%.3f' % (fl, fr, rl, rr))
                        print('[UART SEND] mecanum payload:', payload)

                    try:
                        afs_send(0, payload)
                        last_sent = list(payload)
                        print('[UART SEND] afs_send OK')
                    except Exception as e:
                        print('[UART SEND] afs_send failed:', repr(e))

            time.sleep(poll_interval)
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    run_mecanum_override()
