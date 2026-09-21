# 雑巾装填
# UART1

"""Zoukin Souten controller side.

Poll controller_state, build an 8-byte UART payload, and send it with afs_send.

Payload layout:
1. slido_moter 01 forward PWM
2. slido_moter 01 reverse PWM
3. up_moter 02 forward PWM
4. up_moter 02 reverse PWM
5. Servo power placeholder
6. Servo A/B position
7. Reserved
8. Reserved
"""

from __future__ import annotations

import os
import time
from typing import List, Tuple

from lib.afs_uart import afs_send
from lib import controller_state
from gpiozero import AngularServo
import RPi.GPIO as GPIO
import syoukou
import rerere




UART_DEVICE = os.environ.get("ZOUKIN_SOUTEN_UART_DEVICE", "/dev/ttyAMA1")

MOTOR_SPEED = 150
STOP_PAYLOAD = [0, 0, 0, 0, syoukou.PWM_LIST[0], syoukou.PWM_LIST[1], syoukou.PWM_LIST[2], syoukou.PWM_LIST[3]]  # モーター停止命令

# ===== サーボ設定：ここだけ変更すれば調整できます =====
# BCM番号（物理ピン番号ではありません）
SERVO1_PIN = 18
SERVO2_PIN = 19

# 開く・閉じる位置の角度（-90〜+90）
# 2つのサーボで共通して使う角度を設定します。
HIDARI_OPEN_ANGLE = -30
HIDARI_CLOSED_ANGLE = 20
MIGI_OPEN_ANGLE = 10
MIGI_CLOSED_ANGLE = 35

# プログラムを起動した時点の実際の状態に合わせます。
# Falseなら、最初の丸ボタンで「開く」動作になります。
START_OPEN = False

# SG90の標準的なパルス幅範囲。中点(0度)は1.5msになります。
SERVO_MIN_PULSE_WIDTH = 0.0010
SERVO_MAX_PULSE_WIDTH = 0.0020
CIRCLE_BUTTON_BYTE_INDEX = 0
CIRCLE_BUTTON_MASK = 0b00000010

LIMIT1_PIN = 8  # 右側のリミットスイッチ
LIMIT2_PIN = 12 # 左側のリミットスイッチ
LIMIT3_PIN = 9  # サーボの先のリミットスイッチ
LIMIT_RESEAT_TIMEOUT = 3.0

HIDARI_CYLINDER_FIRE_PARMISSION = False
MIGI_CYLINDER_FIRE_PARMISSION = False


GPIO.setmode(GPIO.BCM)
GPIO.setup(LIMIT1_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(LIMIT2_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(LIMIT3_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)

def fire_cylinder_check():
    "それぞれのエアシリンダが発射可能状態かどうかチェックする"
    global HIDARI_CYLINDER_FIRE_PARMISSION, MIGI_CYLINDER_FIRE_PARMISSION

    if GPIO.input(LIMIT1_PIN) == GPIO.LOW:
        HIDARI_CYLINDER_FIRE_PARMISSION = True
    else:
        HIDARI_CYLINDER_FIRE_PARMISSION = False

    if GPIO.input(LIMIT2_PIN) == GPIO.LOW:
        MIGI_CYLINDER_FIRE_PARMISSION = True
    else:
        MIGI_CYLINDER_FIRE_PARMISSION = False


    return HIDARI_CYLINDER_FIRE_PARMISSION, MIGI_CYLINDER_FIRE_PARMISSION


def _u8(value: int) -> int:
    return max(0, min(255, int(value)))


def _get_values() -> List[int]:
    if controller_state.is_emergency_stopped():
        return []
    vals = controller_state.get_values()
    return list(vals) if vals else []


def _button_pressed(value: int, mask: int) -> bool:
    return (int(value) & mask) != 0


def _circle_pressed(values: List[int]) -> bool:
    if len(values) <= CIRCLE_BUTTON_BYTE_INDEX:
        return False
    return _button_pressed(
        values[CIRCLE_BUTTON_BYTE_INDEX], CIRCLE_BUTTON_MASK
    )


def _send_stop() -> None:
    """モーター停止命令を送る。呼び出し側で送信回数を管理する。"""
    try:
        afs_send(UART_DEVICE, STOP_PAYLOAD)
    except Exception as e:
        print("[UART SEND] stop failed ->", UART_DEVICE, repr(e))

def move_until_limit(payload, limit_pin, poll_interval):
    print("[動作開始] リミットまで移動:", "pin=", limit_pin, "payload=", payload)

    try:
        while GPIO.input(limit_pin) == GPIO.HIGH:
            # 非常停止・コントローラー切断なら中止
            if controller_state.is_emergency_stopped() or not controller_state.get_values():
                return False

            afs_send(UART_DEVICE, payload)
            time.sleep(poll_interval)

        # ここに来たらリミットスイッチが押された
        print("[動作完了] リミット到達: pin=", limit_pin)
        fire_cylinder_check()  # リミットスイッチの状態を更新
        return True

    finally:
        _send_stop()


def move_right_and_reseat_limit(poll_interval: float) -> bool:
    """右方向へ進み、右側リミットを離してから再接触する。"""
    payload = [0, 80, 0, 0, 0, 0, 1, 1]
    deadline = time.monotonic() + LIMIT_RESEAT_TIMEOUT
    released = False
    print("[動作開始] 右側リミットの再位置合わせ")

    try:
        while time.monotonic() < deadline:
            if controller_state.is_emergency_stopped() or not controller_state.get_values():
                return False

            limit_state = GPIO.input(LIMIT1_PIN)
            if limit_state == GPIO.HIGH:
                if not released:
                    print("[動作] 右側リミットから離脱")
                released = True
            elif released and limit_state == GPIO.LOW:
                print("[動作完了] 右側リミットに再接触")
                return True

            afs_send(UART_DEVICE, payload)
            time.sleep(poll_interval)

        print("[LIMIT] right limit reseat timed out")
        return False
    finally:
        _send_stop()


def _motor_from_buttons(forward: bool, reverse: bool) -> Tuple[int, int]:
    """メカナムドライバと同じ正転PWM・逆転PWMのペアを返す。"""
    if forward:
        return 255, 0
    if reverse:
        return 0, 255
    return 0, 0


def move_servo(servo: AngularServo, angle: float) -> bool:
    """角度を直接指定してサーボを動かす。"""
    if angle < -90 or angle > 90:
        return False

    servo.angle = angle
    print("[動作] サーボ移動: angle=", angle)
    return True


def set_servo_open_state(servo1, servo2, is_open: bool) -> None:
    """Set both servos to their configured open or closed position."""
    if is_open:
        servo1_angle = HIDARI_OPEN_ANGLE
        servo2_angle = MIGI_OPEN_ANGLE
        state_name = "OPEN"
    else:
        servo1_angle = HIDARI_CLOSED_ANGLE
        servo2_angle = MIGI_CLOSED_ANGLE
        state_name = "CLOSED"

    if not move_servo(servo1, servo1_angle):
        raise ValueError("SERVO1 angle must be between -90 and +90")
    if not move_servo(servo2, servo2_angle):
        raise ValueError("SERVO2 angle must be between -90 and +90")

    print(
        "[SERVO]",
        state_name,
        "servo1=", servo1_angle,
        "servo2=", servo2_angle,
    )


def _send_payload_for(payload: List[int], seconds: float, poll_interval: float) -> bool:
    """指定したモーター指令を、指定秒数だけ送り続ける。"""
    print("[動作開始] 指定時間モーター動作: seconds=", seconds, "payload=", payload)
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        # 非常停止またはコントローラー切断なら、試運転を中止する。
        if controller_state.is_emergency_stopped() or not controller_state.get_values():
            return False
        try:
            afs_send(UART_DEVICE, payload)
        except Exception as e:
            print("[AUTO TEST] UART send failed ->", UART_DEVICE, repr(e))
            return False
        time.sleep(poll_interval)
    print("[動作完了] 指定時間モーター動作")
    return True


def run_auto_test(servo1, servo2, poll_interval: float, retry_count: int = 0) -> None:
    """実際の動き
    up_moter1:持ち上げるやつ
    slide_moter2:横に動くやつ
    SERVO1:右側のサーボ
    SERVO2:左側のサーボ
    """
    print("[自動装填開始] retry=", retry_count)

    try:
        # サーボを開く。モーターは止めたまま0.40秒待つ。
        move_servo(servo1, HIDARI_OPEN_ANGLE)
        move_servo(servo2, MIGI_OPEN_ANGLE)
        if not _send_payload_for(STOP_PAYLOAD, 0.40, poll_interval):
            return
        # 両方HIGHなら右側リミットをいったん離して再接触させ、最初からやり直す。
        if GPIO.input(LIMIT1_PIN) == GPIO.HIGH and GPIO.input(LIMIT2_PIN) == GPIO.HIGH:
            print("[状態] 両方のリミットスイッチがHIGH。右方向へ移動して再判定します")
            if not move_until_limit([MOTOR_SPEED, 0, 0, 0, syoukou.PWM_LIST[0], syoukou.PWM_LIST[1], syoukou.PWM_LIST[2], syoukou.PWM_LIST[3]], LIMIT1_PIN, poll_interval):
                return

        if GPIO.input(LIMIT1_PIN) == GPIO.LOW:  # もし右側のリミットスイッチにモーターが触れていたなら
            print("[状態] 右側リミット位置として処理を開始")
            # 雑巾保管場所を上げる
            if not move_until_limit([0, 0, 0, MOTOR_SPEED, syoukou.PWM_LIST[0], syoukou.PWM_LIST[1], syoukou.PWM_LIST[2], syoukou.PWM_LIST[3]], LIMIT3_PIN, poll_interval):
                return

            # サーボを閉じる
            move_servo(servo2, MIGI_CLOSED_ANGLE)
            move_servo(servo1, HIDARI_CLOSED_ANGLE)
            time.sleep(0.5)
            stop_list_update()

            # 雑巾保管場所を下げる(下げる時間はまた後で設定)
            if not _send_payload_for([0, 0, MOTOR_SPEED, 0, syoukou.PWM_LIST[0], syoukou.PWM_LIST[1], syoukou.PWM_LIST[2], syoukou.PWM_LIST[3]], 1, poll_interval):
                return
            # 装填機構を左にスライド
            if not move_until_limit([0, MOTOR_SPEED, 0, 0, syoukou.PWM_LIST[0], syoukou.PWM_LIST[1], syoukou.PWM_LIST[2], syoukou.PWM_LIST[3]], LIMIT2_PIN, poll_interval):
                return  
            time.sleep(0.5) 
            # # サーボを開く
            # move_servo(servo2, MIGI_OPEN_ANGLE)
            # if not _send_payload_for(STOP_PAYLOAD, 0.40, poll_interval):
            #     return
        elif GPIO.input(LIMIT2_PIN) == GPIO.LOW:  # もし左側のリミットスイッチにモーターが触れていたなら
            print("[状態] 左側リミット位置として処理を開始")
            # 雑巾保管場所を上げる
            if not move_until_limit([0, 0, 0, MOTOR_SPEED, syoukou.PWM_LIST[0], syoukou.PWM_LIST[1], syoukou.PWM_LIST[2], syoukou.PWM_LIST[3]], LIMIT3_PIN, poll_interval):
                return
            # サーボを閉じる
            move_servo(servo1, HIDARI_CLOSED_ANGLE)
            move_servo(servo2, MIGI_CLOSED_ANGLE)
            time.sleep(0.5)  # サーボが閉じるのを待つ
            # 雑巾保管場所を下げる(下げる時間はまた後で設定)
            if not _send_payload_for([0, 0, MOTOR_SPEED, 0, syoukou.PWM_LIST[0], syoukou.PWM_LIST[1], syoukou.PWM_LIST[2], syoukou.PWM_LIST[3]], 1, poll_interval):
                return
            # 装填機構を横にスライド
            if not move_until_limit([MOTOR_SPEED, 0, 0, 0, syoukou.PWM_LIST[0], syoukou.PWM_LIST[1], syoukou.PWM_LIST[2], syoukou.PWM_LIST[3]], LIMIT1_PIN, poll_interval):
                return
            time.sleep(0.5)  # スライドが完了するのを待つ
        else:
            print("どっちのリミットスイッチにも触れてなくてうぉ。雑巾装填機構がどちら側にあるか確認してください。")
            return
        # サーボを閉じる。モーターは止めたまま0.40秒待つ。
        stop_list_update()
        move_servo(servo1, HIDARI_CLOSED_ANGLE)
        move_servo(servo2, MIGI_CLOSED_ANGLE)
        _send_payload_for(STOP_PAYLOAD, 0.40, poll_interval)
        print("[自動装填完了] 一連の動作が完了しました")
    finally:
        # 終了・非常停止・UARTエラー時のいずれでもモーターを止める。
        _send_stop()

def stop_list_update():
    STOP_PAYLOAD[:] = [0, 0, 0, 0, syoukou.PWM_LIST[0], syoukou.PWM_LIST[1], syoukou.PWM_LIST[2], syoukou.PWM_LIST[3]]  # モーター停止命令


def run_zoukin_souten(poll_interval: float = 0.02):
    last_sent = None
    last_circle_pressed = False
    emergency_stop_sent = False

    print("[UART INIT] Zoukin Souten uses", UART_DEVICE)
    GPIO.setmode(GPIO.BCM)
    servo1 = AngularServo(
        SERVO1_PIN,
        min_angle=-90,
        max_angle=90,
        min_pulse_width=SERVO_MIN_PULSE_WIDTH,
        max_pulse_width=SERVO_MAX_PULSE_WIDTH,
    )
    servo2 = AngularServo(
        SERVO2_PIN,
        min_angle=-90,
        max_angle=90,
        min_pulse_width=SERVO_MIN_PULSE_WIDTH,
        max_pulse_width=SERVO_MAX_PULSE_WIDTH,
    )

    try:
        while True:
            if controller_state.is_emergency_stopped():
                if not emergency_stop_sent:
                    print("[安全停止] モーター停止命令を送信")
                    _send_stop()
                    last_sent = list(STOP_PAYLOAD)
                    emergency_stop_sent = True
                time.sleep(poll_interval)
                continue

            emergency_stop_sent = False
            fire_cylinder_check()
            vals = _get_values()

            circle_pressed = _circle_pressed(vals)

            # ○を押した瞬間だけ、上の run_auto_test() を1回実行する。
            # ○による通常のサーボ開閉トグルは使わない。
            if circle_pressed and not last_circle_pressed:
                print("[AUTO TEST] start")
                run_auto_test(servo1, servo2, poll_interval)
                stop_list_update()
                payload = STOP_PAYLOAD
            else:
                payload = STOP_PAYLOAD
                if rerere.RERERE_MODE == False:
                    stop_list_update()
                    # 通常時は十字キーでモーターを操作する。

            if payload != last_sent:
                print("[UART SEND] payload:", payload)
                last_sent = list(payload)

            try:
                afs_send(UART_DEVICE, payload)
                # print("[UART SEND] afs_send OK ->", UART_DEVICE)
            except Exception as e:
                print("[UART SEND] afs_send failed ->", UART_DEVICE, repr(e))

            time.sleep(poll_interval)
    except KeyboardInterrupt:
        pass
    finally:
        _send_stop()
        servo1.close()
        servo2.close()


run_receiver = run_zoukin_souten


if __name__ == "__main__":
    run_zoukin_souten()