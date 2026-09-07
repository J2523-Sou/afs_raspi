# 一括実行

import threading
import time
from http.server import ThreadingHTTPServer

from controller_receive import run_receiver
from air_cylinder import run_air_cylinder
from mecanum import run_mecanum
from zoukin_souten import run_zoukin_souten
from debug_server import Handler as DebugHandler

MAX_SPEED = 0.4


def main():
    controller_receiver = threading.Thread(target=run_receiver, daemon=True)
    air_cylinder = threading.Thread(target=run_air_cylinder, daemon=True)
    mecanum = threading.Thread(target=run_mecanum, kwargs={"max_speed": MAX_SPEED}, daemon=True)
    zoukin_souten = threading.Thread(target=run_zoukin_souten, daemon=True)
    debug_server = threading.Thread(
        target=ThreadingHTTPServer(("0.0.0.0", 8080), DebugHandler).serve_forever,
        daemon=True,
    )

    controller_receiver.start()
    air_cylinder.start()
    mecanum.start()
    zoukin_souten.start()
    debug_server.start()
    print("Debug dashboard: http://0.0.0.0:8080")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Stopping all threads (process will exit).")


if __name__ == "__main__":
    main()
