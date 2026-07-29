import threading
import time

from controller_receive import run_receiver
from mecanum import run_mecanum
from yamaguchi import run_yamaguchi

# ここで最大スピードを調整します（0.0〜1.0）
MAX_SPEED = 0.4


def main():
    controller_receiver = threading.Thread(target=run_receiver, daemon=True)
    mecanum = threading.Thread(
        target=run_mecanum,
        kwargs={"max_speed": MAX_SPEED},
        daemon=True,
    )
    yamaguchi = threading.Thread(target=run_yamaguchi, daemon=True)

    controller_receiver.start()
    mecanum.start()
    yamaguchi.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Stopping all threads (process will exit).")


if __name__ == "__main__":
    main()