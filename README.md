# afs_raspi

Raspberry Pi から AFS の各機構を制御する Python プログラムです。DualSense の入力を TCP で受信し、メカナム駆動・山口機構・エアシリンダーへ UART で出力します。

## 構成

- `controller_receive.py` — コントローラー入力の TCP 受信（ポート `5001`）
- `mecanum.py` / `mecanum_override.py` — メカナム機構の制御
- `yamaguchi.py` — 山口機構の制御
- `cylinder.py` — DualSense の L2/R2 による2本のエアシリンダー制御
- `debug_server.py` — デバッグ用サーバー
- `lib/` — コントローラー状態と PIC 通信用 UART の共通処理
- `run_all.py` — 上記機構をスレッドでまとめて起動

## 必要環境

- Raspberry Pi
- Python 3.11 以降
- `lgpio`（コントローラー受信時の LED 制御に使用。利用できない環境では警告を出して続行）
- PIC と接続された UART

## 実行

コントローラー送信側から Raspberry Pi の TCP `5001` 番ポートへ接続できる状態で、次を実行します。

```bash
python3 run_all.py
```

エアシリンダー単体の動作確認は次のコマンドで実行できます。

```bash
python3 cylinder.py
```

終了するには `Ctrl+C` を押してください。シリンダー制御は終了時に全出力を `0` にします。

## コントローラーフレーム

受信側は次の2形式に対応しています。

- `0xAA` + 7 bytes: 従来形式。`buttons2` の L2/R2 ビットを使用
- `0xAB` + 9 bytes: 拡張形式。末尾の `l2` / `r2` アナログ値（0〜255）を使用

拡張形式では、L2 がシリンダー2、R2 がシリンダー1に対応します。トリガー値が 50% 以上になると、対応する PIC 出力（PWM21/PWM22）が `255` になります。2本のシリンダーは同時に動作できます。

UART の割り当ては、メカナムが UART0、山口機構が UART1、エアシリンダーが UART2 です。

## テスト

ハードウェアに接続せず、シリンダーの入力変換と PIC ペイロード生成をテストできます。

```bash
python3 -m unittest test_cylinder_control.py
```

## 注意

実機で起動する前に、UART 番号、GPIO 番号、PIC 側の PWM 割り当てが使用する機体の配線と一致していることを確認してください。
