"""
Tyokkakun - シンプルなモーター制御

メカナム計算を使わずに、直接PWM値を設定してモーターを制御します。
"""

import time
from lib.afs_uart import afs_send
from lib import controller_state


def axis_to_pwm(value: float) -> int:
    """-1.0 ~ 1.0 の値を 0 ~ 255 のPWM値に変換"""
    return int(value * 127 + 128)


def run_tyokkakun(poll_interval: float = 0.02):
    """
    コントローラーのスティック値を読み取り、
    直接PWMを計算してモーターを制御するメインループ
    
    スティック値の読み取り方:
    - controller_state.get_values() で7バイトのデータを取得
    - vals[3]: 左スティックX (バイト値 0-255)
    - vals[4]: 左スティックY (バイト値 0-255)
    - vals[5]: 右スティックX (バイト値 0-255)
    - vals[6]: 右スティックY (バイト値 0-255)
    
    UART送信方法:
    - afs_send(0, [pwm1, pwm2, ..., pwm8]) で8バイト送信
    - フォーマット: [前進PWM, 後進PWM, 前進PWM, 後進PWM, ...] × 4ホイール
    """
    
    last_sent = None
    
    try:
        while True:
            # 1. コントローラーの値を取得
            vals = controller_state.get_values()
            
            if not vals:
                time.sleep(poll_interval)
                continue
            
            # 2. スティック値を読み取り (7バイトフォーマット)
            # バイト値をそのままPWMとして使用（-1.0~1.0変換なし）
            if len(vals) >= 7:
                # 左スティック: 前進/後進
                left_x = vals[3]   # 0-255
                left_y = vals[4]   # 0-255
                # 右スティック: 回転
                right_x = vals[5]  # 0-255
                right_y = vals[6]  # 0-255
            else:
                left_x = vals[0] if len(vals) > 0 else 128
                left_y = vals[1] if len(vals) > 1 else 128
                right_x = vals[2] if len(vals) > 2 else 128
                right_y = vals[3] if len(vals) > 3 else 128
            
            # 3. シンプルにPWMを直接設定
            # 例: 左スティックYで前進/後進、右スティックXで回転
            # PWMフォーマット: [fl_f, fl_r, fr_f, fr_r, rl_f, rl_r, rr_f, rr_r]
            
            # 前進/後進 (128が停止、0-127が後進、129-255が前進)
            forward_pwm = left_y
            # 回転 (128が停止)
            rotate_pwm = right_x
            
            # 4つのホイールに同じPWMを設定
            payload = [
                forward_pwm, 0,      # フロント左
                forward_pwm, 0,      # フロント右
                forward_pwm, 0,      # リア左
                forward_pwm, 0       # リア右
            ]
            
            # 5. UART送信
            if payload != last_sent:
                print(f"[TYOKKAKUN] left_y={left_y} right_x={right_x}")
                print(f"[UART SEND] payload: {payload}")
                try:
                    afs_send(0, payload)
                    last_sent = list(payload)
                    print("[UART SEND] OK")
                except Exception as e:
                    print(f"[UART SEND] failed: {e}")
            
            time.sleep(poll_interval)
            
    except KeyboardInterrupt:
        print("Stopping tyokkakun...")


if __name__ == "__main__":
    run_tyokkakun()
