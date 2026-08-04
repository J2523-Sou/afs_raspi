import socket
try:
    import lgpio
except Exception:
    lgpio = None

from lib import controller_state

# GPIO（ピン）
led1 = 17
h = None
if lgpio is not None:
    try:
        h = lgpio.gpiochip_open(0)
        lgpio.gpio_claim_output(h, led1)
    except Exception as e:
        print("Warning: cannot open gpiochip:", e)
        h = None

HOST = "0.0.0.0"
PORT = 5001


def _set_led(value):
    if h is not None:
        try:
            lgpio.gpio_write(h, led1, value)
        except Exception:
            pass


def _recv_exact(conn, size):
    data = bytearray()
    while len(data) < size:
        chunk = conn.recv(size - len(data))
        if not chunk:
            return None
        data.extend(chunk)
    return bytes(data)


def run_receiver():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((HOST, PORT))
        server.listen(1)

        while True:
            print("Waiting for connection...")
            conn, addr = server.accept()
            print("Connected from", addr)
            _set_led(1)

            try:
                with conn:
                    while True:
                        # ヘッダーを探し、その後の7バイトが揃うまで受信する。
                        head = _recv_exact(conn, 1)
                        if head is None:
                            break
                        if head[0] != 0xAA:
                            continue

                        receive = _recv_exact(conn, 7)
                        if receive is None:
                            break
                        controller_state.set_values(receive)
            except OSError as e:
                print("Controller connection error:", e)
            finally:
                # 切断直後から古い操作値を使わせない。
                controller_state.clear_values()
                _set_led(0)
                print("Controller disconnected")


if __name__ == "__main__":
    run_receiver()
