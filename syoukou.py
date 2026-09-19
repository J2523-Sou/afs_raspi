from gpiozero import RotaryEncoder, DigitalInputDevice
import time

from lib import controller_state

NORMAL_SPEED = 200
POLL_INTERVAL = 0.02

PWM_LIST = [0, 0, 0, 0]  # PWM出力のリスト。4つのモーターに対応する。

ZENTAI_NAGASA = 1000

MIGI_ITI = 0
HIDARI_ITI = 0

TOP_OR_UNDER = 0

TOL = 300  # 許容誤差の範囲


# GPIOピンの指定 (A相を17番、B相を27番に繋いだ場合の例)
# BCM番号(GPIO番号)で指定します
right_pin_a = 2
right_pin_b = 3
left_pin_a = 11
# 左側はB相が未結線のため、B相用のピン番号は使用しない

LEFT_ENCODER_REVERSED = True  # 左エンコーダは配線の都合上、常に逆向きに回転する


def _button_pressed(value, mask):
    return (int(value) & mask) != 0


class SingleChannelEncoder:
    """A相のみでパルスをカウントする簡易エンコーダ。

    通常のロータリーエンコーダはA相・B相の位相差から回転方向を
    判定するが、左側はB相が未結線のため方向の自動判定ができない。
    そこで、パルス数だけをA相1本でカウントし、回転方向は
    呼び出し側(set_directionメソッド)から現在の運転方向
    (上昇中か下降中か)を渡して加算/減算を切り替える。
    """

    def __init__(self, pin_a, reversed_direction: bool = False):
        self.steps = 0
        self._direction = 1  # 1: 上昇方向(+1ずつ加算), -1: 下降方向(-1ずつ加算)
        # reversed_direction=Trueの場合、物理的な逆回転を吸収するために
        # 符号を反転させる。以降、呼び出し側は配線の向きを気にせず
        # set_direction(1)=上昇, set_direction(-1)=下降 とだけ指定すればよい
        self._sign = -1 if reversed_direction else 1
        self._pin = DigitalInputDevice(pin_a)
        self._pin.when_activated = self._count_pulse

    def _count_pulse(self):
        self.steps += self._direction * self._sign

    def set_direction(self, direction: int):
        """direction: 1(上昇) または -1(下降) を指定する"""
        self._direction = direction

    def close(self):
        self._pin.close()


def left_motor_pwm(migi_iti, hidari_iti):
    # 左右の位置差に応じて左モーターのPWM値を補正する
    return NORMAL_SPEED - (hidari_iti - migi_iti) / (255 / ZENTAI_NAGASA)


def top_or_under(migi_iti, hidari_iti):
    # 右エンコーダの位置から、現在「上端付近」か「それ以外」かを判定する
    global TOP_OR_UNDER
    ITI_update()
    if migi_iti > ZENTAI_NAGASA - TOL:
        TOP_OR_UNDER = 1
    else:
        TOP_OR_UNDER = 0


def ITI_update():
    # 左右エンコーダの現在値をグローバル変数に反映する
    global MIGI_ITI, HIDARI_ITI
    MIGI_ITI = right_encoder.steps
    HIDARI_ITI = left_encoder.steps


def run_syoukou(poll_interval: float = POLL_INTERVAL):
    """コントローラーの上ボタンで昇降用のPWM出力を制御する。

    PWM_LISTへの書き込みまでがこのプログラムの役割で、
    実際のUART送信は別プログラムが行う想定。
    """
    # wrap=Falseで上限なくカウント。max_steps=0で制限なし
    global right_encoder, left_encoder
    right_encoder = RotaryEncoder(right_pin_a, right_pin_b, wrap=False, max_steps=0)
    # 左側はB相が未結線のため、A相のみのSingleChannelEncoderを使用する
    left_encoder = SingleChannelEncoder(left_pin_a, reversed_direction=LEFT_ENCODER_REVERSED)

    try:
        global PWM_LIST
        while True:
            values = controller_state.get_values()
            button_bytes = values[1] if len(values) > 1 else 0
            is_up_pressed = _button_pressed(button_bytes, 0b00001000)
            is_down_pressed = _button_pressed(button_bytes, 0b00000100)
            ITI_update()

            if controller_state.is_emergency_stopped() or not values:
                PWM_LIST[:] = [0, 0, 0, 0]
            elif is_up_pressed and TOP_OR_UNDER == 0:
                # 上昇方向に動くので、左エンコーダのカウント方向を+1に設定
                # (物理的な逆回転の吸収はSingleChannelEncoder側で処理済み)
                left_encoder.set_direction(1)
                # 一度上ボタンが押されたら、ボタンを離しても
                # 目標位置(ZENTAI_NAGASA - TOL)に届くまで動き続ける仕様
                while MIGI_ITI < ZENTAI_NAGASA - TOL:
                    ITI_update()
                    PWM_LIST = [0, NORMAL_SPEED, 0, left_motor_pwm(MIGI_ITI, HIDARI_ITI)]
                    print(f"現在の状況:上昇中, 右エンコーダ: {MIGI_ITI}, 左エンコーダ: {HIDARI_ITI}, PWM: {PWM_LIST}")
                    if controller_state.is_emergency_stopped():
                        break  # 緊急停止時は直ちにループを抜ける
                    time.sleep(poll_interval)

            elif is_down_pressed and TOP_OR_UNDER == 1:
                # 下降方向に動くので、左エンコーダのカウント方向を-1に設定
                # (物理的な逆回転の吸収はSingleChannelEncoder側で処理済み)
                left_encoder.set_direction(-1)
                # 上昇時と同様、一度下ボタンが押されたら
                # 目標位置(TOL)に届くまで動き続ける仕様
                while MIGI_ITI > TOL:
                    ITI_update()
                    print(f"現在の状況:下降中, 右エンコーダ: {MIGI_ITI}, 左エンコーダ: {HIDARI_ITI}, PWM: {PWM_LIST}")
                    if controller_state.is_emergency_stopped():
                        break  # 緊急停止時は直ちにループを抜ける
                    time.sleep(poll_interval)
                    PWM_LIST[:] = [NORMAL_SPEED, 0, left_motor_pwm(MIGI_ITI, HIDARI_ITI), 0]
            else:
                PWM_LIST[:] = [0, 0, 0, 0]

            top_or_under(MIGI_ITI, HIDARI_ITI)
            time.sleep(poll_interval)
    except KeyboardInterrupt:
        print("\n終了します")
    finally:
        PWM_LIST[:] = [0, 0, 0, 0]
        right_encoder.close()
        left_encoder.close()


if __name__ == "__main__":
    run_syoukou()