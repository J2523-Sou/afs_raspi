import zoukin_souten
import mecanum
import controller_receive
import air_cylinder
from lib import controller_state
import time
import threading
import signal
import sys

idou_kyori = 0.6  # 秒数を指定してください
MASK = 6

# ===== 暴走禁止（安全装置）関連の設定 =====
# 発射許可待ちなど、外部の状態変化を待つ処理がこの秒数を超えても
# 終わらない場合は「暴走」とみなして強制停止する
RUNAWAY_TIMEOUT = 5.0

# グローバル変数の初期化
RERERE_MODE = False
RERERE_SOUTEN = False
previous_button_state = False

# 「次にどちら側の装填・発射を行うか」を一元管理する変数。
# ※ どちらを動かすかは必ずこの変数だけで判断する。
#    zoukin_souten側のフラグ(HIDARI/MIGI_CYLINDER_FIRE_PARMISSION)は
#    「その側が物理的に準備できているか」の確認だけに使い、
#    どちらを動かすかの決定には使わない。
current_direction = "left"


def stop_all_motors():
    """モーター出力を完全に停止するヘルパー関数"""
    try:
        mecanum.afs_send([0, 0, 0, 0, 0, 0, 0, 0])
    except Exception as e:
        print(f"モーター停止中にエラーが発生しましたが終了処理を続行します: {e}")


def get_current_side_permission():
    """
    current_direction に対応する側の発射許可フラグを返す。
    どちら側を動かすかは current_direction が決定し、
    このフラグはその側の準備確認にのみ使う。
    """
    if current_direction == "left":
        return zoukin_souten.HIDARI_CYLINDER_FIRE_PARMISSION
    else:
        return zoukin_souten.MIGI_CYLINDER_FIRE_PARMISSION


def reset_rerere_state():
    """
    れれれモード開始時（トグルON時）に呼び出す初期化・リセット関数。
    モーターを止め、内部状態を初期値（左スタート）に戻す。
    """
    global current_direction
    print("[初期化] れれれモードの状態をリセットします。")
    stop_all_motors()
    current_direction = "left"  # 必ず左側からスタートする

    # air_cylinder側にリセット関数があれば呼び出す（無ければ何もしない）
    try:
        air_cylinder.zioud_sylinder_reset()
    except AttributeError:
        pass
    except Exception as e:
        print(f"シリンダーのリセット中にエラーが発生しましたが続行します: {e}")


def cleanup(signum=None, frame=None):
    """
    プログラム終了時に必ず呼び出される安全停止（クリーンアップ）関数
    """
    print("\n[安全装置] プログラムの終了を検知しました。全機構を停止・初期化します。")
    stop_all_motors()
    sys.exit(0)


def update_controller_state():
    """
    コントローラーの値を読み取り、非常停止やモード切り替えを監視する関数
    戻り値: 続行可能なら True、非常停止などで中断すべきなら False
    """
    global RERERE_MODE, previous_button_state, current_direction

    # 1. 非常停止のチェック
    if controller_state.is_emergency_stopped():
        print("非常停止が有効です。モーター出力を停止します。")
        stop_all_motors()
        RERERE_MODE = False
        return False

    values = controller_state.get_values()
    if not values or len(values) < 4:
        return True  # 値がうまく取れなくてもプログラムは続行

    # 2. ボタンの立ち上がりエッジ（押された瞬間）を検出してトグル
    current_button_state = (values[2] == MASK)

    if current_button_state and not previous_button_state:
        RERERE_MODE = not RERERE_MODE
        if RERERE_MODE:
            print("レレレうちモードを開始します。初期化を実行します。")
            reset_rerere_state()
        else:
            print("レレレうちモードを終了します。動作をリセット・停止します。")
            current_direction = "left"  # 次回の動作を左に設定
            stop_all_motors()  # モードオフ時に確実にモーターを止める

    previous_button_state = current_button_state
    return True


def wait_with_update(seconds):
    """
    指定された時間(seconds)待機するが、その間も細かくコントローラーを監視する関数。
    """
    global RERERE_MODE
    start_time = time.time()

    while time.time() - start_time < seconds:
        if not update_controller_state():
            return False
        if not RERERE_MODE:
            return False
        time.sleep(0.05)

    return True


def wait_for_fire_permission():
    """
    現在の側（current_direction）の発射許可が出るまで待機する。
    ・暴走禁止: RUNAWAY_TIMEOUT秒を超えたら強制停止してFalseを返す
    ・モードOFFや非常停止を検知した場合も即座にFalseを返す
    戻り値: 発射してよければ True、中断すべきなら False
    """
    global RERERE_MODE
    wait_start = time.time()

    while not get_current_side_permission():
        if not update_controller_state():
            return False
        if not RERERE_MODE:
            return False

        if time.time() - wait_start > RUNAWAY_TIMEOUT:
            print(f"[暴走禁止] {current_direction}側の発射許可待ちが{RUNAWAY_TIMEOUT}秒を超えました。安全のため停止します。")
            stop_all_motors()
            RERERE_MODE = False
            return False

        time.sleep(0.05)

    return True


def run_rerere():
    global RERERE_MODE, RERERE_SOUTEN, current_direction

    print("れれれシステム起動!")

    # try...finally でエラー時も確実に終了処理を行う
    try:
        while True:
            # 常にコントローラーの状態を更新
            update_controller_state()

            if RERERE_MODE:
                # current_direction の側の発射許可を待つ（暴走禁止タイムアウト付き）
                if not wait_for_fire_permission():
                    stop_all_motors()
                    continue

                air_cylinder.zioud_sylinder_fire()

                if not wait_with_update(0.5):
                    stop_all_motors()
                    continue

                # 変数 current_direction を使って左右の動作を判断する
                if current_direction == "left":
                    zoukin_souten.load_cloth_to_left()
                    mecanum.zidou_mecanum("左", 1, idou_kyori)

                    if not wait_with_update(idou_kyori):
                        stop_all_motors()
                        continue
                    if not wait_with_update(idou_kyori):
                        stop_all_motors()
                        continue

                    print("左への装填が完了しました。次は右へ動きます。")
                    current_direction = "right"  # 次回の動作を右に設定

                elif current_direction == "right":
                    zoukin_souten.load_cloth_to_right()
                    mecanum.zidou_mecanum("右", 1, idou_kyori)

                    if not wait_with_update(idou_kyori):
                        stop_all_motors()
                        continue
                    if not wait_with_update(idou_kyori):
                        stop_all_motors()
                        continue

                    print("右への装填が完了しました。次は左へ動きます。")
                    current_direction = "left"  # 次回の動作を左に設定

                if not wait_with_update(1.0):
                    stop_all_motors()
                    continue

            else:
                time.sleep(0.05)

    except Exception as e:
        # プログラム内で予期せぬエラー（バグなど）が起きた場合
        print(f"\n[エラー] 予期せぬエラーが発生しました: {e}")
    finally:
        # エラーで落ちた場合でも、通常の終了でも、絶対にここを通る
        cleanup()


if __name__ == "__main__":
    # Ctrl+Cやkillコマンドでも必ずcleanupが呼ばれるようにする（暴走禁止の一環）
    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)
    run_rerere()