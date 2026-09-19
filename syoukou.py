from gpiozero import RotaryEncoder
import time

from lib import controller_state
from lib.afs_uart import afs_send_tail

NORMAL_SPEED = 30
POLL_INTERVAL = 0.02

PWM_LIST = [0, 0, 0, 0]  # PWM出力のリスト。4つのモーターに対応する。



# GPIOピンの指定 (A相を17番、B相を27番に繋いだ場合の例)
# BCM番号(GPIO番号)で指定します
# pin_a = 2
# pin_b = 3

def _button_pressed(value, mask):
    return (int(value) & mask) != 0


def run_syoukou(poll_interval: float = POLL_INTERVAL):
    """コントローラーの上ボタンで昇降用のUART1出力を制御する。"""
    # wrap=Falseで上限なくカウント。max_steps=0で制限なし
    encoder = RotaryEncoder(pin_a, pin_b, wrap=False, max_steps=0)

    try:
        global PWM_LIST
        while True:
            values = controller_state.get_values()
            button_bytes = values[1] if len(values) > 1 else 0
            is_up_pressed = _button_pressed(button_bytes, 0b00001000)

            if controller_state.is_emergency_stopped() or not values:
                PWM_LIST = [0, 0, 0, 0]
            elif is_up_pressed:
                PWM_LIST = [NORMAL_SPEED, 0, 0, 0]
            else:
                PWM_LIST = [0, 0, 0, 0]

            time.sleep(poll_interval)
    except KeyboardInterrupt:
        print("\n終了します")
    finally:
        PWM_LIST = [0, 0, 0, 0]
        encoder.close()


if __name__ == "__main__":
    run_syoukou()