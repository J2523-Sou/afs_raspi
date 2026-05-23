import time
import socket
try:
    import lgpio
except Exception:
    lgpio = None

from lib import controller_state

# GPIO
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


def run_receiver():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind((HOST, PORT))
    s.listen(1)

    print("Waiting for connection...")
    conn, addr = s.accept()
    print("Connected from", addr)
    if h is not None:
        try:
            lgpio.gpio_write(h, led1, 1)
        except Exception:
            pass

    try:
        while True:

            #Header
            head = conn.recv(1)
            if not head:
                break
            if head[0] != 0xAA:
                continue

            # Get 7Byte data
            receive = conn.recv(7)
            if len(receive) != 7:
                continue
            data = list(receive)
            controller_state.set_values(data)

            time.sleep(0.0001)
    finally:
        conn.close()
        s.close()


if __name__ == "__main__":
    run_receiver()