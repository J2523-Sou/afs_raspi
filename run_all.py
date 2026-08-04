import threading
import time

from controller_receive import run_receiver
from mecanum import run_mecanum
from zoukin_souten import run_zoukin_souten

# ここで最大スピードを調整します（0.0〜1.0）
MAX_SPEED = 0.4


def main():
    controller_receiver = threading.Thread(target=run_receiver, daemon=True)
    mecanum = threading.Thread(
        target=run_mecanum,
        kwargs={"max_speed": MAX_SPEED},
        daemon=True,
    )
    zoukin_souten = threading.Thread(target=run_zoukin_souten, daemon=True)

    controller_receiver.start()
    mecanum.start()
    zoukin_souten.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Stopping all threads (process will exit).")


if __name__ == "__main__":
    main()
