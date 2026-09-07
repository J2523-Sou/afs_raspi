# AFS Raspberry Pi Controller

Raspberry Pi上でAFSロボットのコントローラー入力を受信し、メカナム4輪・雑巾装填・エアシリンダーを制御するプログラムです。

## 環境構築

以下は Raspberry Pi OS などのLinux環境での手順です。プロジェクトの取得から実行まで、時系列で記載しています。

### 1. リポジトリを取得する

```bash
git clone <リポジトリのURL>
cd afs_raspi
```

すでにプロジェクトを取得済みの場合は、プロジェクトのディレクトリへ移動します。

```bash
cd /path/to/afs_raspi
```

### 2. Pythonとvenvを準備する

`venv`の作成に必要なパッケージをインストールします。

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip
```

### 3. 仮想環境を作成する

プロジェクト直下に `.venv` という名前で仮想環境を作成します。

```bash
python3 -m venv .venv
```

### 4. 仮想環境を有効化する

```bash
source .venv/bin/activate
```

有効化すると、ターミナルの先頭に `(.venv)` と表示されます。以降のPythonコマンドは、この仮想環境を有効化した状態で実行してください。

### 5. `pip`を更新する

```bash
python -m pip install --upgrade pip
```

### 6. `requirements.txt`をインストールする

```bash
python -m pip install -r requirements.txt
```

### 7. プログラムを起動する

全機能をまとめて起動します。

```bash
python run_all.py
```

デバッグダッシュボードは、ブラウザーで次のURLを開いて確認できます。

```text
http://<Raspberry PiのIPアドレス>:8080
```

同じRaspberry Pi上のブラウザーから確認する場合は、`http://localhost:8080` でもアクセスできます。

### 8. プログラムを停止する

実行中のターミナルで `Ctrl+C` を押してください。

### 9. 次回以降の起動

仮想環境の作成と依存関係のインストールは初回のみで構いません。次回からは、プロジェクトディレクトリへ移動して仮想環境を有効化した後、プログラムを起動します。

```bash
cd /path/to/afs_raspi
source .venv/bin/activate
python run_all.py
```

作業終了後に仮想環境を終了する場合は、次を実行します。

```bash
deactivate
```

## 主なファイル

- `run_all.py`: 各機能をまとめて起動
- `controller_receive.py`: コントローラー入力の受信
- `mecanum.py`: メカナム4輪の制御
- `zoukin_souten.py`: 雑巾装填の制御
- `air_cylinder.py`: エアシリンダーの制御
- `debug_server.py`: ポート `8080` のデバッグダッシュボード
