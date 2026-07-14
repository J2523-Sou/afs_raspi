import time
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

# 0xAA は従来の7バイト形式、0xAB は末尾にL2/R2を追加した形式。
# 拡張形式: [buttons0, buttons1, buttons2, lx, ly, rx, ry, l2, r2]
FRAME_LENGTHS = {
    0xAA: 7,
    0xAB: 9,
}


def _recv_exact(conn, length):
    """TCPからlengthバイトを、分割受信を考慮して読み込む。"""
    chunks = bytearray()
    while len(chunks) < length:
        chunk = conn.recv(length - len(chunks))
        if not chunk:
            return None
        chunks.extend(chunk)
    return bytes(chunks)


def _receive_frame(conn):
    """次の有効なコントローラーフレームを受信する。"""
    while True:
        head = _recv_exact(conn, 1)
        if head is None:
            return None

        data_length = FRAME_LENGTHS.get(head[0])
        if data_length is None:
            continue

        return _recv_exact(conn, data_length)


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
            receive = _receive_frame(conn)
            if receive is None:
                break

            data = list(receive)
            controller_state.set_values(data)

            time.sleep(0.0001)
    finally:
        # 切断後に最後の入力（特にトリガー）が残らないようにする。
        controller_state.set_values([])
        conn.close()
        s.close()


if __name__ == "__main__":
    run_receiver()
