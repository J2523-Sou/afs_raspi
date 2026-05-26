import threading
import time

from controller_receive import run_receiver
from mecanum import run_mecanum


def main():
    controller_receiver = threading.Thread(target=run_receiver, daemon=True)
    mecanum = threading.Thread(target=run_mecanum, daemon=True)

    controller_receiver.start()
    mecanum.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Stopping all threads (process will exit).")


if __name__ == "__main__":
    main()
