import zoukin_souten
import mecanum
import controller_receive
import air_cylinder
from lib import controller_state
import time
import threading
import signal
import sys

idou_kyori = 0.8 # 秒数を指定してください
MASK = 6

# グローバル変数の初期化
RERERE_MODE = False
RERERE_SOUTEN = False
previous_button_state = False
current_direction = "left"  # 追加: 次にどちらに動くかを管理する変数

def stop_all_motors():
    """モーター出力を完全に停止するヘルパー関数"""
    try:
        mecanum.afs_send([0, 0, 0, 0, 0, 0, 0, 0])
    except Exception as e:
        print(f"モーター停止中にエラーが発生しましたが終了処理を続行します: {e}")

def cleanup(signum=None, frame=None):
    """
    プログラム終了時に必ず呼び出される安全停止（クリーンアップ）関数
    """
    print("\n[安全装置] プログラムの終了を検知しました。全機構を停止・初期化します。")
    stop_all_motors()
    
    # 必要であればここにシリンダーを戻す処理や、フラグの初期化を追加してください
    # 例: air_cylinder.return_to_home() 
    # 例: zoukin_souten.reset()
    
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
        return True # 値がうまく取れなくてもプログラムは続行
        
    # 2. ボタンの立ち上がりエッジ（押された瞬間）を検出してトグル
    current_button_state = (values[2] == MASK)
    
    if current_button_state and not previous_button_state:
        RERERE_MODE = not RERERE_MODE
        if RERERE_MODE:
            print("レレレうちモードを開始します。初期化を実行します。")
            # 開始時のリセット処理
            current_direction = "left"  # モード開始時は必ず左からスタートさせる
            
        else:
            print("レレレうちモードを終了します。動作をリセット・停止します。")
            stop_all_motors() # モードオフ時に確実にモーターを止める
            
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

def run_rerere():
    global RERERE_MODE, RERERE_SOUTEN, current_direction
    

    print("れれれシステム起動!")

    # try...finally でエラー時も確実に終了処理を行う
    try:
        while True:
            # 常にコントローラーの状態を更新
            update_controller_state()
            
            if RERERE_MODE:
                while not (zoukin_souten.MIGI_CYLINDER_FIRE_PARMISSION or zoukin_souten.HIDARI_CYLINDER_FIRE_PARMISSION):
                    if not update_controller_state(): # 待機中も非常停止を監視
                        break
                    time.sleep(0.05)
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
    run_rerere()