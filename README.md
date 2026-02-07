# BT Metadata Collector

Bluetooth AVRCP メタデータをリアルタイムに受信・記録するツール。

Raspberry Pi を Bluetooth オーディオレシーバー（A2DP Sink）として動作させ、各種デバイス（iPhone / Mac / Windows / Android）から送信される AVRCP メタデータ（曲名、アーティスト名、アルバム名等）をセッション単位で収集・保存する。

## 構成

- **Raspberry Pi 4**: Bluetooth レシーバー + Web サーバー
- **記録用 Mac**: ブラウザで操作（`http://<RPi IP>:8000`）
- **コンテンツ再生端末**: iPhone / Mac / Windows / Android

## セットアップ

Raspberry Pi の初期セットアップ手順は [docs/raspi-setup.md](docs/raspi-setup.md) を参照。

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

### systemd サービス

```bash
sudo cp bt-metadata-collector.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable bt-metadata-collector
sudo systemctl start bt-metadata-collector
```

## 使い方

1. ブラウザで `http://<RPi IP>:8000` にアクセス
2. コンテンツ名、プラットフォーム、端末、OS を選択して「セッション開始」
3. 対象端末で音楽や動画を再生 → メタデータがリアルタイム表示される
4. 「セッション終了 → ログ保存」で JSONL ファイルに保存

## 技術スタック

- Python 3.11+ / FastAPI / Jinja2
- SSE (sse-starlette) + htmx
- BlueZ D-Bus API (dbus-python + PyGObject)
- カスタム CSS（ダークテーマ）

## ログ形式

`data/` ディレクトリに JSONL 形式で保存。詳細は [docs/initial-spec.md](docs/initial-spec.md) セクション 7 を参照。
