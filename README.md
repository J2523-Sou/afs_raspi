# afs_raspi

`afs_raspi` は、Raspberry Pi を中心にロボットの各機構を統合制御するための Python プログラムです。操作者が使用する DualSense の入力を TCP で受信し、Raspberry Pi 上で機構ごとの制御処理に分配します。各制御処理は独立したスレッドとして動作し、PIC などの下位コントローラーへ UART 経由で指令を送信します。

この構成により、コントローラー入力の受信処理と、メカナム走行・山口機構・エアシリンダーなどの機構制御を分離しています。`run_all.py` を起動すると、対応する機構をまとめて動かせます。また、各機構の Python ファイルを直接起動することで、個別の動作確認もできます。

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

## 実行方法

### 1. Raspberry Pi 側の準備

リポジトリを Raspberry Pi に配置し、プロジェクトディレクトリへ移動します。

```bash
git clone https://github.com/J2523-Sou/afs_raspi.git
cd afs_raspi
```

必要な Python パッケージを環境に合わせてインストールします。`lgpio` が未インストールでも、GPIO の LED 制御を使わない環境では警告を表示して起動できます。

```bash
python3 -m pip install lgpio
```

### 2. コントローラー送信側を接続

コントローラー送信側から Raspberry Pi の IP アドレスへ TCP 接続できることを確認します。受信サーバーは TCP ポート `5001` を使用します。

Raspberry Pi 側でポートを確認する場合は、次のように実行できます。

```bash
hostname -I
```

### 3. 全機構を起動

PIC、UART、電源、コントローラー送信側が準備できた状態で、次を実行します。

```bash
python3 run_all.py
```

`run_all.py` は、コントローラー受信、メカナム、山口機構、エアシリンダー、デバッグサーバーをそれぞれスレッドで起動します。

### 個別に起動

機構単位で確認する場合は、対象のファイルを直接実行します。

```bash
python3 controller_receive.py  # コントローラー受信のみ
python3 cylinder.py            # エアシリンダー制御
python3 mecanum.py             # メカナム制御
python3 yamaguchi.py           # 山口機構制御
```

エアシリンダー単体の動作確認は次のコマンドで実行できます。

```bash
python3 cylinder.py
```

終了するには `Ctrl+C` を押してください。シリンダー制御は終了時に全出力を `0` にします。

### 起動確認

起動後、コンソールに `Waiting for connection...` が表示されれば、コントローラーからの接続待ち状態です。接続されると接続元アドレスが表示されます。

接続できない場合は、次の点を確認してください。

- Raspberry Pi とコントローラー送信側が同じネットワークに接続されているか
- 送信先 IP アドレスと TCP ポート `5001` が正しいか
- Raspberry Pi のファイアウォールで TCP `5001` が遮断されていないか
- UART のデバイス番号と PIC の配線が一致しているか

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
