"""Air cylinder control entry point.

L / R ボタンのどちらかが押された瞬間だけ、UARTで発射命令を送る。
"""

from __future__ import annotations

import importlib
import os
import time

from lib import controller_state


UART_DEVICE = os.environ.get("AIR_CYLINDER_UART_DEVICE", "/dev/ttyAMA0")
BAUDRATE = int(os.environ.get("AIR_CYLINDER_BAUDRATE", "9600"))
TIMEOUT = float(os.environ.get("AIR_CYLINDER_TIMEOUT", "0.1"))

# どのバイトのどのビットを見るか。
# いまは controller_state の 0 番目のバイトに入る L / R ボタンを見ている。
# 必要ならここだけ変えれば、別のボタンに差し替えられる。
BUTTON_BYTE_INDEX = int(os.environ.get("AIR_CYLINDER_BUTTON_BYTE_INDEX", "0"))
BUTTON_MASK_L = int(os.environ.get("AIR_CYLINDER_BUTTON_MASK_L", "16"), 0)
BUTTON_MASK_R = int(os.environ.get("AIR_CYLINDER_BUTTON_MASK_R", "32"), 0)

# 送るデータは必要最低限の2パターンだけにする。
# 実機側の仕様が決まったら、この2つだけ直せばよい。
HIGH_PAYLOAD = [255, 0, 0, 0, 0, 0, 0]
LOW_PAYLOAD = [0, 255, 0, 0, 0, 0, 0]


def _load_serial_module():
	try:
		return importlib.import_module("serial")
	except ModuleNotFoundError as exc:
		raise RuntimeError("pyserial が必要です。pip で pyserial をインストールしてください") from exc


def _open_serial():
	serial = _load_serial_module()
	return serial.Serial(UART_DEVICE, BAUDRATE, timeout=TIMEOUT)


def _button_pressed():
	# controller_state に入っている最新の入力値を読む。
	values = controller_state.get_values()
	if not values or len(values) <= BUTTON_BYTE_INDEX:
		return False

	# L か R のどちらかが 1 なら「押されている」とみなす。
	button_byte = int(values[BUTTON_BYTE_INDEX])
	return (button_byte & BUTTON_MASK_L) != 0 or (button_byte & BUTTON_MASK_R) != 0


def _send_frame(ser, payload):
	# 0xAA を先頭につけて、7バイトのフレームとして送る。
	ser.write(bytes([0xAA, *payload]))
	ser.flush()


def run_air_cylinder(poll_interval: float = 0.02):
	print("[UART INIT] Air cylinder uses", UART_DEVICE)
	print("[BUTTON] byte_index=%d L=0x%02X R=0x%02X" % (BUTTON_BYTE_INDEX, BUTTON_MASK_L, BUTTON_MASK_R))

	# HIGH / LOW のどちらを出すかを保持する。
	is_high = False
	# 押しっぱなしで何回も切り替わらないように、前回の押下状態も覚える。
	last_pressed = False

	while True:
		try:
			with _open_serial() as ser:
				print("[UART INIT] connected")
				try:
					# 接続直後に現在状態を一度送る。
					_send_frame(ser, HIGH_PAYLOAD if is_high else LOW_PAYLOAD)
					print("[UART SEND] initial state:", "HIGH" if is_high else "LOW")
				except Exception as e:
					print("[UART SEND] initial state failed:", repr(e))
				while True:
					pressed = _button_pressed()

					# 押された瞬間だけ反応する。
					# 押し続けている間は反応しないので、1回押したら1回だけ発射する。
					if pressed and not last_pressed:
						is_high = not is_high
						payload = HIGH_PAYLOAD if is_high else LOW_PAYLOAD
						print("[BUTTON] L/R pressed ->", "HIGH" if is_high else "LOW")
						try:
							# ここで空気圧シリンダーへ発射命令を送る。
							_send_frame(ser, payload)
							print("[UART SEND] payload:", payload)
						except Exception as e:
							print("[UART SEND] failed:", repr(e))

					last_pressed = pressed

					time.sleep(poll_interval)

		except KeyboardInterrupt:
			break
		except Exception as e:
			print("[UART ERROR]", repr(e))
			time.sleep(1.0)


if __name__ == "__main__":
	run_air_cylinder()
