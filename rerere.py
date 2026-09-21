import zoukin_souten
import mecanum
import controller_receive
import air_cylinder
from lib import controller_state
import time

idou_kyori = 1 #秒数を指定してください

RERERE_MODE = False

def run_rerere():
    while True:
        # コントローラーの状態を取得
        controller_state = controller_receive.get_values()

        if controller_state.is_emergency_stopped():
            print("非常停止が有効です。モーター出力を停止します。")
            mecanum.afs_send([0, 0, 0, 0, 0, 0, 0, 0])
            break
        if controller_state.is_l2_pressed() and controller_state.is_r2_pressed():
            '''レレレうちをする
            1 レレレうちモードの変数をオンにする
            2 発射できる方を発射する
            3 装填しながら横に動く
            4 停止もう一度オンにするモードが押されたら変数をオフにして終了する
                '''
            while True:
                RERERE_MODE = True
                air_cylinder._handle_cylinder_firing()
                if zoukin_souten.HIDARI_CYLINDER_FIRE_PARMISSION:
                    mecanum.zidou_mecanum("右", 200, idou_kyori)
                    zoukin_souten.run_auto_test()
                elif zoukin_souten.MIGI_CYLINDER_FIRE_PARMISSION:
                    mecanum.ziodu_mecanum("左", 200, idou_kyori)
                    zoukin_souten.run_auto_test()

                if controller_state.is_emergency_stopped():
                    print("非常停止が有効です。モーター出力を停止します。")
                    mecanum.afs_send([0, 0, 0, 0, 0, 0, 0, 0])
                    break

                if controller_state.is_l2_pressed() and controller_state.is_r2_pressed():
                    print("レレレうちモードを終了します。")
                    RERERE_MODE = False
                    break

                time.sleep(1)  # ループの間隔を調整するために少し待機
            
                        

if __name__ == "__main__":
    run_rerere()