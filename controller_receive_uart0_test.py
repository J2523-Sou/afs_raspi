import time

from lib.afs_uart import afs_send
from lib import controller_state


def run_sender(poll_interval=0.02):
    """Poll `controller_state.get_values()` and send UART when data changes.

    WiFi の受信は `controller_receive.py` に任せ、ここでは共有状態を監視して
    A ボタンの状態に応じて uart0 に 8 バイトを送信する。
    """
    last = None
    try:
        while True:
            vals = controller_state.get_values()
            if vals and vals != last:
                last = list(vals)
                # vals は WiFi 側で受信した 7 バイト
                a_pressed = bool(vals[0] & 0x01)
                payload = [255 if a_pressed else 0, 0, 0, 0, 0, 0, 0, 0]
                print("[UART SEND] payload:", payload)
                try:
                    afs_send(0, payload)
                    print("[UART SEND] afs_send OK")
                except Exception as e:
                    print("[UART SEND] afs_send failed:", repr(e))
            time.sleep(poll_interval)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    run_sender()