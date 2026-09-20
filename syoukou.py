from gpiozero import RotaryEncoder, DigitalInputDevice
import time

from lib import controller_state

# ==========================================
# デバッグモード（ボタンの信号を調べるためのスイッチ）
# True にすると、ボタンを押した時に画面に信号（2進数）が表示されます
# ==========================================
DEBUG_BUTTONS = True

NORMAL_SPEED = 200
POLL_INTERVAL = 0.02

PWM_LIST = [0, 0, 0, 0]  # PWM出力のリスト。4つのモーターに対応する。

ZENTAI_NAGASA = 4000
MIGI_ITI = 0
HIDARI_ITI = 0
TOL = 300  # 許容誤差の範囲

# コントローラーのボタン割り当てマスク
UP_BTN_MASK   = 0b00001000
DOWN_BTN_MASK = 0b00010000

# 【重要】ここに、画面に表示されたパッドボタンの信号（0b...）を書き込んでください
PAD_BTN_MASK  = 0b10000000

right_pin_a = 2
right_pin_b = 3
left_pin_a = 11

KP = 1.2  # 追従の感度

def _button_pressed(value, mask):
    return (int(value) & mask) != 0

class SingleChannelEncoder:
    def __init__(self, pin_a, reversed_direction: bool = False):
        self.steps = 0
        self._direction = 1 
        self._sign = -1 if reversed_direction else 1
        self._pin = DigitalInputDevice(pin_a)
        self._pin.when_activated = self._count_pulse

    def _count_pulse(self):
        self.steps += self._direction * self._sign

    def set_direction(self, direction: int):
        self._direction = direction

    def close(self):
        self._pin.close()

def left_motor_pwm(migi_iti, hidari_iti, direction=1):
    diff = migi_iti - hidari_iti
    
    if direction == 1:
        pwm = NORMAL_SPEED + (diff * KP)
    else:
        pwm = NORMAL_SPEED - (diff * KP)
    
    MIN_SPEED = 100 
    clamped_pwm = max(MIN_SPEED, min(255, int(pwm)))
    
    return clamped_pwm

def ITI_update():
    global MIGI_ITI, HIDARI_ITI
    MIGI_ITI = right_encoder.steps
    HIDARI_ITI = left_encoder.steps

def run_syoukou(poll_interval: float = POLL_INTERVAL):
    global right_encoder, left_encoder
    right_encoder = RotaryEncoder(right_pin_a, right_pin_b, wrap=False, max_steps=0)
    left_encoder = SingleChannelEncoder(left_pin_a, reversed_direction=False) 

    last_button_bytes = -1  # デバッグ表示用の変数

    try:
        global PWM_LIST
        while True:
            values = controller_state.get_values()
            button_bytes = values[1] if values and len(values) > 1 else 0
            
            # --- ボタン信号の確認用プリント ---
            if DEBUG_BUTTONS and button_bytes != last_button_bytes:
                if button_bytes != 0:
                    print(f"現在のボタン信号: {bin(button_bytes)}")
                last_button_bytes = button_bytes
            # --------------------------------

            is_up_pressed = _button_pressed(button_bytes, UP_BTN_MASK)
            is_down_pressed = _button_pressed(button_bytes, DOWN_BTN_MASK)
            is_pad_pressed = _button_pressed(button_bytes, PAD_BTN_MASK)

            ITI_update()

            if controller_state.is_emergency_stopped() or not values:
                PWM_LIST[:] = [0, 0, 0, 0]

            # -----------------------------------------------------------
            # パッドボタンを押している間の「手動モード」
            # （位置制限は無視するが、自動追従は有効）
            # -----------------------------------------------------------
            elif is_pad_pressed:
                if is_up_pressed:
                    left_encoder.set_direction(1)
                    PWM_LIST[:] = [0, NORMAL_SPEED, 0, left_motor_pwm(MIGI_ITI, HIDARI_ITI, 1)]
                elif is_down_pressed:
                    left_encoder.set_direction(-1)
                    PWM_LIST[:] = [NORMAL_SPEED, 0, left_motor_pwm(MIGI_ITI, HIDARI_ITI, -1), 0]
                else:
                    PWM_LIST[:] = [0, 0, 0, 0]
                    left_encoder.steps = right_encoder.steps

            # -----------------------------------------------------------
            # 従来通りの「自動モード」（パッドボタンを押していない時）
            # -----------------------------------------------------------
            elif is_up_pressed and MIGI_ITI < ZENTAI_NAGASA - TOL:
                left_encoder.set_direction(1)
                while MIGI_ITI < ZENTAI_NAGASA - TOL:
                    if controller_state.is_emergency_stopped():
                        break
                        
                    current_values = controller_state.get_values()
                    current_btn = current_values[1] if current_values and len(current_values) > 1 else 0
                    if _button_pressed(current_btn, PAD_BTN_MASK):
                        break

                    ITI_update()
                    PWM_LIST[:] = [0, NORMAL_SPEED, 0, left_motor_pwm(MIGI_ITI, HIDARI_ITI, 1)]
                    time.sleep(poll_interval)
                    
                left_encoder.steps = right_encoder.steps

            elif is_down_pressed and MIGI_ITI > TOL:
                left_encoder.set_direction(-1)
                while MIGI_ITI > TOL:
                    if controller_state.is_emergency_stopped():
                        break
                        
                    current_values = controller_state.get_values()
                    current_btn = current_values[1] if current_values and len(current_values) > 1 else 0
                    if _button_pressed(current_btn, PAD_BTN_MASK):
                        break

                    ITI_update()
                    PWM_LIST[:] = [NORMAL_SPEED, 0, left_motor_pwm(MIGI_ITI, HIDARI_ITI, -1), 0]
                    time.sleep(poll_interval)
                    
                left_encoder.steps = right_encoder.steps
                    
            else:
                PWM_LIST[:] = [0, 0, 0, 0]

            time.sleep(poll_interval)
            
    except KeyboardInterrupt:
        print("\n終了します")
    finally:
        PWM_LIST[:] = [0, 0, 0, 0]
        right_encoder.close()
        left_encoder.close()

if __name__ == "__main__":
    run_syoukou()