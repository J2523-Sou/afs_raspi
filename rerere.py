import zoukin_souten
import mecanum
import controller_receive
import air_cylinder
from lib import controller_state
import time
import threading

idou_kyori = 1 # 秒数を指定してください
MASK = 6

# グローバル変数の初期化
RERERE_MODE = False
RERERE_SOUTEN = False
previous_button_state = False

def update_controller_state():
    """
    コントローラーの値を読み取り、非常停止やモード切り替えを監視する関数
    戻り値: 続行可能なら True、非常停止などで中断すべきなら False
    """
    global RERERE_MODE, previous_button_state
    
    # 1. 非常停止のチェック
    if controller_state.is_emergency_stopped():
        print("非常停止が有効です。モーター出力を停止します。")
        mecanum.afs_send([0, 0, 0, 0, 0, 0, 0, 0])
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
            print("レレレうちモードを開始します。")
        else:
            print("レレレうちモードを終了します。")
            
    previous_button_state = current_button_state
    return True

def wait_with_update(seconds):
    """
    指定された時間(seconds)待機するが、その間も細かくコントローラーを監視する関数。
    モードが途中でオフにされたり、非常停止された場合は False を返して待機を中断する。
    """
    global RERERE_MODE
    start_time = time.time()
    
    while time.time() - start_time < seconds:
        if not update_controller_state():
            return False # 非常停止がかかった
        if not RERERE_MODE:
            return False # ボタンによってモードが終了された
        time.sleep(0.05)
        
    return True

def run_rerere():
    global RERERE_MODE, RERERE_SOUTEN
    
    print("れれれシステム起動!")

    while True:
        # 常にコントローラーの状態を更新
        update_controller_state()
        
        if RERERE_MODE:
            # ---------------------------
            # レレレ撃ち 1サイクルの動作
            # ---------------------------
            air_cylinder.zioud_sylinder_fire()
            print("シリンダーを発射しました。装填しながら横に移動します。")
            
            # 待機中も監視し、中断されたら次のループへスキップ(continue)
            if not wait_with_update(0.5):
                continue
                
            if zoukin_souten.HIDARI_CYLINDER_FIRE_PARMISSION:
                zoukin_souten.load_cloth_to_left()
                mecanum.zidou_mecanum("左", 1, idou_kyori)
                if not wait_with_update(idou_kyori): continue
                
                if not wait_with_update(idou_kyori): continue
                print("装填が完了しました。")
                
            elif zoukin_souten.MIGI_CYLINDER_FIRE_PARMISSION:
                zoukin_souten.load_cloth_to_right()
                mecanum.zidou_mecanum("右", 1, idou_kyori)
                if not wait_with_update(idou_kyori): continue
                
                
                if not wait_with_update(idou_kyori): continue
                print("装填が完了しました。")
             
            # ループの間隔を調整するための待機（中断可能）
            wait_with_update(1.0)
            
        else:
            # モード待機中は少しだけ休む（CPU負荷軽減）
            time.sleep(0.05)

if __name__ == "__main__":
    run_rerere()