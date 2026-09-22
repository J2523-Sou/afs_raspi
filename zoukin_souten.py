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
HIDARI_OPEN_ANGLE = -30
HIDARI_CLOSED_ANGLE = 20
MIGI_OPEN_ANGLE = 10
MIGI_CLOSED_ANGLE = 35

START_OPEN = False

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

# ==========================================
# 外部プログラム連携用のグローバル変数と関数
# ==========================================
REQUESTED_DIRECTION = None

def load_cloth_to_left():
    """別プログラムから『左に装填』を実行するための関数"""
    global REQUESTED_DIRECTION
    REQUESTED_DIRECTION = "left"

def load_cloth_to_right():
    """別プログラムから『右に装填』を実行するための関数"""
    global REQUESTED_DIRECTION
    REQUESTED_DIRECTION = "right"
# ==========================================


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
            if controller_state.is_emergency_stopped() or not controller_state.get_values():
                return False
            afs_send(UART_DEVICE, payload)
            time.sleep(poll_interval)

        print("[動作完了] リミット到達: pin=", limit_pin)
        fire_cylinder_check()  # リミットスイッチの状態を更新
        return True

    finally:
        _send_stop()

def move_servo(servo: AngularServo, angle: float) -> bool:
    """角度を直接指定してサーボを動かす。"""
    if angle < -90 or angle > 90:
        return False
    servo.angle = angle
    print("[動作] サーボ移動: angle=", angle)
    return True

def _send_payload_for(payload: List[int], seconds: float, poll_interval: float) -> bool:
    """指定したモーター指令を、指定秒数だけ送り続ける。"""
    print("[動作開始] 指定時間モーター動作: seconds=", seconds, "payload=", payload)
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
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

def rack_idou(poll_interval):
    '''移動できる方にラックを強制的に移動させる'''
    if GPIO.input(LIMIT1_PIN) == GPIO.HIGH:
        print("[状態] 右側リミットへ移動します")
        if not move_until_limit([MOTOR_SPEED, 0, 0, 0, syoukou.PWM_LIST[0], syoukou.PWM_LIST[1], syoukou.PWM_LIST[2], syoukou.PWM_LIST[3]], LIMIT1_PIN, poll_interval):
            return
    elif GPIO.input(LIMIT2_PIN) == GPIO.HIGH:
        print("[状態] 左側リミットへ移動します")
        if not move_until_limit([0, MOTOR_SPEED, 0, 0, syoukou.PWM_LIST[0], syoukou.PWM_LIST[1], syoukou.PWM_LIST[2], syoukou.PWM_LIST[3]], LIMIT2_PIN, poll_interval):
            return

def servo_open(servo1, servo2):
    '''サーボを開く'''
    move_servo(servo1, HIDARI_OPEN_ANGLE)
    move_servo(servo2, MIGI_OPEN_ANGLE)


def run_souten_direction(servo1, servo2, direction: str, poll_interval: float) -> None:
    """指定された方向（左または右）に確実に装填を行うための関数"""
    print(f"[自動装填開始] 指定方向: {direction}")
    
    try:
        # まずサーボを開く
        move_servo(servo1, HIDARI_OPEN_ANGLE)
        move_servo(servo2, MIGI_OPEN_ANGLE)
        if not _send_payload_for(STOP_PAYLOAD, 0.40, poll_interval):
            return

        if direction == "left":
            # 左に装填する場合：まず右(LIMIT1)に雑巾を取りに行く
            if GPIO.input(LIMIT1_PIN) == GPIO.HIGH:
                print("[状態] 右側リミットへ移動します")
                if not move_until_limit([MOTOR_SPEED, 0, 0, 0, syoukou.PWM_LIST[0], syoukou.PWM_LIST[1], syoukou.PWM_LIST[2], syoukou.PWM_LIST[3]], LIMIT1_PIN, poll_interval):
                    return
            
            print("[状態] 右側(LIMIT1)から左側(LIMIT2)へ装填を開始します")
            # 雑巾保管場所を上げる
            if not move_until_limit([0, 0, 0, MOTOR_SPEED, syoukou.PWM_LIST[0], syoukou.PWM_LIST[1], syoukou.PWM_LIST[2], syoukou.PWM_LIST[3]], LIMIT3_PIN, poll_interval):
                return
            
            # サーボを閉じる
            move_servo(servo2, MIGI_CLOSED_ANGLE)
            move_servo(servo1, HIDARI_CLOSED_ANGLE)
            time.sleep(0.5)
            stop_list_update()

            # 雑巾保管場所を下げる
            if not _send_payload_for([0, 0, MOTOR_SPEED, 0, syoukou.PWM_LIST[0], syoukou.PWM_LIST[1], syoukou.PWM_LIST[2], syoukou.PWM_LIST[3]], 1, poll_interval):
                return
            
            # 装填機構を左にスライド
            if not move_until_limit([0, MOTOR_SPEED, 0, 0, syoukou.PWM_LIST[0], syoukou.PWM_LIST[1], syoukou.PWM_LIST[2], syoukou.PWM_LIST[3]], LIMIT2_PIN, poll_interval):
                return  
            time.sleep(0.5)

        elif direction == "right":
            # 右に装填する場合：まず左(LIMIT2)に雑巾を取りに行く
            if GPIO.input(LIMIT2_PIN) == GPIO.HIGH:
                print("[状態] 左側リミットへ移動します")
                if not move_until_limit([0, MOTOR_SPEED, 0, 0, syoukou.PWM_LIST[0], syoukou.PWM_LIST[1], syoukou.PWM_LIST[2], syoukou.PWM_LIST[3]], LIMIT2_PIN, poll_interval):
                    return

            print("[状態] 左側(LIMIT2)から右側(LIMIT1)へ装填を開始します")
            # 雑巾保管場所を上げる
            if not move_until_limit([0, 0, 0, MOTOR_SPEED, syoukou.PWM_LIST[0], syoukou.PWM_LIST[1], syoukou.PWM_LIST[2], syoukou.PWM_LIST[3]], LIMIT3_PIN, poll_interval):
                return
            
            # サーボを閉じる
            move_servo(servo1, HIDARI_CLOSED_ANGLE)
            move_servo(servo2, MIGI_CLOSED_ANGLE)
            time.sleep(0.5) 
            stop_list_update()

            # 雑巾保管場所を下げる
            if not _send_payload_for([0, 0, MOTOR_SPEED, 0, syoukou.PWM_LIST[0], syoukou.PWM_LIST[1], syoukou.PWM_LIST[2], syoukou.PWM_LIST[3]], 1, poll_interval):
                return
            
            # 装填機構を右にスライド
            if not move_until_limit([MOTOR_SPEED, 0, 0, 0, syoukou.PWM_LIST[0], syoukou.PWM_LIST[1], syoukou.PWM_LIST[2], syoukou.PWM_LIST[3]], LIMIT1_PIN, poll_interval):
                return
            time.sleep(0.5)

        # 最後にサーボを閉じる
        stop_list_update()
        move_servo(servo1, HIDARI_CLOSED_ANGLE)
        move_servo(servo2, MIGI_CLOSED_ANGLE)
        _send_payload_for(STOP_PAYLOAD, 0.40, poll_interval)
        print("[自動装填完了] 指定方向への装填が完了しました")

    finally:
        _send_stop()



def run_auto_test(servo1, servo2, poll_interval: float, retry_count: int = 0) -> None:
    """現在の位置を基準に行う元の自動装填ロジック (○ボタン用)"""
    print("[自動装填開始] retry=", retry_count)
    try:
        move_servo(servo1, HIDARI_OPEN_ANGLE)
        move_servo(servo2, MIGI_OPEN_ANGLE)
        if not _send_payload_for(STOP_PAYLOAD, 0.40, poll_interval):
            return
            
        if GPIO.input(LIMIT1_PIN) == GPIO.HIGH and GPIO.input(LIMIT2_PIN) == GPIO.HIGH:
            print("[状態] 両方のリミットスイッチがHIGH。右方向へ移動して再判定します")
            if not move_until_limit([MOTOR_SPEED, 0, 0, 0, syoukou.PWM_LIST[0], syoukou.PWM_LIST[1], syoukou.PWM_LIST[2], syoukou.PWM_LIST[3]], LIMIT1_PIN, poll_interval):
                return

        if GPIO.input(LIMIT1_PIN) == GPIO.LOW:  
            print("[状態] 右側リミット位置として処理を開始")
            if not move_until_limit([0, 0, 0, MOTOR_SPEED, syoukou.PWM_LIST[0], syoukou.PWM_LIST[1], syoukou.PWM_LIST[2], syoukou.PWM_LIST[3]], LIMIT3_PIN, poll_interval):
                return
            move_servo(servo2, MIGI_CLOSED_ANGLE)
            move_servo(servo1, HIDARI_CLOSED_ANGLE)
            time.sleep(0.5)
            stop_list_update()

            if not _send_payload_for([0, 0, MOTOR_SPEED, 0, syoukou.PWM_LIST[0], syoukou.PWM_LIST[1], syoukou.PWM_LIST[2], syoukou.PWM_LIST[3]], 1, poll_interval):
                return
            if not move_until_limit([0, MOTOR_SPEED, 0, 0, syoukou.PWM_LIST[0], syoukou.PWM_LIST[1], syoukou.PWM_LIST[2], syoukou.PWM_LIST[3]], LIMIT2_PIN, poll_interval):
                return  
            time.sleep(0.5) 
            
        elif GPIO.input(LIMIT2_PIN) == GPIO.LOW: 
            print("[状態] 左側リミット位置として処理を開始")
            if not move_until_limit([0, 0, 0, MOTOR_SPEED, syoukou.PWM_LIST[0], syoukou.PWM_LIST[1], syoukou.PWM_LIST[2], syoukou.PWM_LIST[3]], LIMIT3_PIN, poll_interval):
                return
            move_servo(servo1, HIDARI_CLOSED_ANGLE)
            move_servo(servo2, MIGI_CLOSED_ANGLE)
            time.sleep(0.5) 
            
            if not _send_payload_for([0, 0, MOTOR_SPEED, 0, syoukou.PWM_LIST[0], syoukou.PWM_LIST[1], syoukou.PWM_LIST[2], syoukou.PWM_LIST[3]], 1, poll_interval):
                return
            if not move_until_limit([MOTOR_SPEED, 0, 0, 0, syoukou.PWM_LIST[0], syoukou.PWM_LIST[1], syoukou.PWM_LIST[2], syoukou.PWM_LIST[3]], LIMIT1_PIN, poll_interval):
                return
            time.sleep(0.5) 
        else:
            print("どっちのリミットスイッチにも触れてなくてうぉ。雑巾装填機構がどちら側にあるか確認してください。")
            return
            
        stop_list_update()
        move_servo(servo1, HIDARI_CLOSED_ANGLE)
        move_servo(servo2, MIGI_CLOSED_ANGLE)
        _send_payload_for(STOP_PAYLOAD, 0.40, poll_interval)
        print("[自動装填完了] 一連の動作が完了しました")
    finally:
        _send_stop()

def stop_list_update():
    STOP_PAYLOAD[:] = [0, 0, 0, 0, syoukou.PWM_LIST[0], syoukou.PWM_LIST[1], syoukou.PWM_LIST[2], syoukou.PWM_LIST[3]]

def run_zoukin_souten(poll_interval: float = 0.02):
    global REQUESTED_DIRECTION
    last_sent = None
    last_circle_pressed = False
    emergency_stop_sent = False

    print("[UART INIT] Zoukin Souten uses", UART_DEVICE)
    GPIO.setmode(GPIO.BCM)
    servo1 = AngularServo(SERVO1_PIN, min_angle=-90, max_angle=90, min_pulse_width=SERVO_MIN_PULSE_WIDTH, max_pulse_width=SERVO_MAX_PULSE_WIDTH)
    servo2 = AngularServo(SERVO2_PIN, min_angle=-90, max_angle=90, min_pulse_width=SERVO_MIN_PULSE_WIDTH, max_pulse_width=SERVO_MAX_PULSE_WIDTH)

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
            controller_atai = controller_state.get_values()

            if circle_pressed and not last_circle_pressed: 
                print("[AUTO TEST] start")
                run_auto_test(servo1, servo2, poll_interval)
                stop_list_update()
                payload = STOP_PAYLOAD
                
            # ========== 新しく追加した外部指示の処理 ==========
            elif REQUESTED_DIRECTION == "left":
                run_souten_direction(servo1, servo2, "left", poll_interval)
                REQUESTED_DIRECTION = None
                stop_list_update()
                payload = STOP_PAYLOAD
                time.sleep(0.2)
                
            elif REQUESTED_DIRECTION == "right":
                run_souten_direction(servo1, servo2, "right", poll_interval)
                REQUESTED_DIRECTION = None
                stop_list_update()
                payload = STOP_PAYLOAD
                time.sleep(0.2)
            # ==================================================
            elif vals and len(vals) > 0 and vals[0] == 8:
                rack_idou(poll_interval)
                stop_list_update()
                payload = STOP_PAYLOAD
                time.sleep(0.2)
            elif vals and len(vals) > 0 and vals[0] == 1:
                servo_open(servo1, servo2)
                stop_list_update()
                payload = STOP_PAYLOAD
                time.sleep(0.2)
            else:
                payload = STOP_PAYLOAD
                if rerere.RERERE_MODE == False:
                    stop_list_update()

            if payload != last_sent:
                print("[UART SEND] payload:", payload)
                last_sent = list(payload)

            try:
                afs_send(UART_DEVICE, payload)
            except Exception as e:
                print("[UART SEND] afs_send failed ->", UART_DEVICE, repr(e))

            time.sleep(poll_interval)
            last_circle_pressed = circle_pressed
            
    except KeyboardInterrupt:
        pass
    finally:
        _send_stop()
        servo1.close()
        servo2.close()

run_receiver = run_zoukin_souten

if __name__ == "__main__":
    run_zoukin_souten()