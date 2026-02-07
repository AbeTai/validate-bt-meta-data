# BT Metadata Collector

Bluetooth AVRCP メタデータをリアルタイムに受信・記録するツール。

Raspberry Pi を Bluetooth オーディオレシーバー（A2DP Sink）として動作させ、各種デバイス（iPhone / Mac / Windows / Android）から送信される AVRCP メタデータ（曲名、アーティスト名、アルバム名等）をセッション単位で収集・保存する。

## 構成

- **Raspberry Pi 4**: Bluetooth レシーバー + Web サーバー
- **記録用端末**: ブラウザで操作（Mac / Windows / Linux / iPad 等、ブラウザがあれば何でも可）
- **コンテンツ再生端末**: iPhone / Mac / Windows / Android

## セットアップ

Raspberry Pi の初期セットアップ手順は [docs/raspi-setup.md](docs/raspi-setup.md) を参照。

### セットアップ時の注意点

- **Bluetooth デバイス名の設定**: `/etc/bluetooth/main.conf` の `Name` 設定は `hostname` プラグインに上書きされる。デバイス名を変更するには `/etc/machine-info` に `PRETTY_HOSTNAME=BT-MetadataCollector` を設定する
- **ペアリング時の Authorize service 確認**: ペアリング時に `Authorize service` の確認プロンプトが表示されたら、必ず `yes` と回答する。AVRCP サービスの認可が行われないとメタデータが取得できない
- **Ghostty ターミナルの場合**: SSH 接続時に `nano` 等が動作しない場合は `export TERM=xterm-256color` を `~/.bashrc` に追加する

## 起動方法

### モックモード（開発・テスト用）

```bash
source .venv/bin/activate
BT_MOCK=true uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### 実機モード

```bash
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### systemd サービス（自動起動）

```bash
sudo cp bt-metadata-collector.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable bt-metadata-collector
sudo systemctl start bt-metadata-collector
```

## 初期セットアップ完了後の使い方

### 1. RPi を起動する

systemd サービスを登録済みなら、電源を入れるだけでサーバーが自動起動する。

手動起動の場合:
```bash
ssh pi@bt-collector.local
cd ~/bt-metadata-collector
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### 2. コンテンツ再生端末を Bluetooth 接続する

- 対象端末（iPhone 等）の Bluetooth 設定から「BT-MetadataCollector」に接続
- 既にペアリング済み＋trust 済みなら自動接続される

### 3. ブラウザで Web UI を開く

同じネットワーク上の任意の端末（Mac / Windows / Linux / iPad 等）のブラウザで:

```
http://bt-collector.local:8000
```

> Windows で `.local` が解決できない場合は、RPi の IP アドレスを直接使用: `http://<RPi の IP>:8000`

### 4. セッションを記録する

1. **コンテンツ名**を入力（例: Spotify, YouTube, Apple Music）
2. **Web or アプリ**を選択
3. **コンテンツ再生端末**を選択 → OS 選択肢が自動で絞り込まれる
4. **「セッション開始」** をクリック
5. 対象端末でコンテンツを再生 → メタデータがリアルタイムでフィードに表示される
6. 記録が終わったら **「セッション終了 → ログ保存」** をクリック
7. `data/` ディレクトリに JSONL ファイルが保存される

### 5. ログファイルを取得する

**方法 1: Web UI から（どの端末でも可）**

セッション一覧のファイル名をクリック → 新しいタブにテキスト表示される。コピーまたは `Cmd+S` / `Ctrl+S` で保存。

**方法 2: SCP でコピー（Mac / Linux）**

```bash
# 全ファイルをまとめてコピー
scp pi@bt-collector.local:~/bt-metadata-collector/data/*.jsonl ~/Downloads/

# 特定のファイルのみ
scp pi@bt-collector.local:~/bt-metadata-collector/data/<ファイル名>.jsonl ~/Downloads/
```

### 出先での利用（iPhone テザリング）

事前に RPi に iPhone テザリングの Wi-Fi を登録しておけば、出先でも利用可能。詳しくは [docs/raspi-setup.md](docs/raspi-setup.md) セクション 8 を参照。

## AVRCP メタデータについて

### 取得できるフィールド

| フィールド | 説明 |
|-----------|------|
| Title | 曲名・動画名 |
| Artist | アーティスト名 |
| Album | アルバム名 |
| Genre | ジャンル |
| TrackNumber | トラック番号 |
| NumberOfTracks | 総トラック数 |
| Duration | 再生時間（ミリ秒） |
| Status | playing / paused / stopped |

### 既知の挙動

- **AVRCP にはソースアプリの識別子がない** — どのアプリで再生しているかはメタデータからは判定できない。Web UI のセッション入力で人間が指定する設計
- **アプリによってメタデータの充実度が異なる** — 例: iPhone の YouTube アプリは全フィールドが null になるが、Web 版（Safari）は取得できる。この違いを調査するのが本ツールの目的
- **同一サービスでも OS による差がある** — Android の YouTube は Album を空にすることが多い等

## 技術スタック

- Python 3.11+ / FastAPI / Jinja2
- SSE (sse-starlette) + htmx
- BlueZ D-Bus API (dbus-python + PyGObject)
- カスタム CSS（ダークテーマ）

## ログ形式

`data/` ディレクトリに JSONL 形式で保存。詳細は [docs/initial-spec.md](docs/initial-spec.md) セクション 7 を参照。

## トラブルシューティング

### メタデータが表示されない

1. `busctl tree org.bluez | grep player` で MediaPlayer1 が存在するか確認
2. 存在しない場合は、端末のペアリングを解除して再ペアリング（`Authorize service` に `yes` と回答）
3. `dbus-monitor --system "sender='org.bluez'"` で D-Bus シグナルが来ているか確認

### Bluetooth デバイスが見つからない

```bash
bluetoothctl
power on
discoverable on
pairable on
```

### サーバーの状態確認

```bash
# systemd サービスのステータス
sudo systemctl status bt-metadata-collector

# ログ確認
journalctl -u bt-metadata-collector -f

# ヘルスチェック API
curl http://localhost:8000/health
```
