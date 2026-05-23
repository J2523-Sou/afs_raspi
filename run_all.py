import threading
import time

from controller_receive import run_receiver
from controller_receive_uart0_test import run_sender


def main():
    controller_receiver = threading.Thread(target=run_receiver, daemon=True)
    sender_1_test = threading.Thread(target=run_sender, daemon=True)

    controller_receiver.start()
    sender_1_test.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Stopping all threads (process will exit).")


if __name__ == "__main__":
    main()
