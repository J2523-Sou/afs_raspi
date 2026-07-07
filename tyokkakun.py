import time
from lib.afs_uart import afs_send
from lib import controller_state

def get_controller_signals():

    vals = controller_state.get_values()

    if not vals:
        return None
    
    if len(vals) >= 7:
        left_x = vals[3]   # 0-255
        left_y = vals[4]   # 0-255

    else:
        left_x = vals[0] if len(vals) > 0 else 128
        left_y = vals[1] if len(vals) > 1 else 128

    return left_x, left_y

print("実行開始")
try:
    while True:
        result = get_controller_signals()

        if result:
            lx, ly = result
            print(f"Xの値:{lx}, Yの値:{ly}")
            payload = [lx, ly, 0, 0, 0, 0, 0, 0]
            afs_send(1, payload)
            time.sleep(0.02)
        else:
            print("コントローラーの値が取得できませんでした。")
            time.sleep(0.1)

except KeyboardInterrupt:
    print("終了します")