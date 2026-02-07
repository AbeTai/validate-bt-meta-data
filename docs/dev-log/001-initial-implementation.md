# 001: 初期実装 — BT Metadata Collector 全機能構築

**日付**: 2026-02-07

## 概要

`docs/initial-spec.md` の仕様書に基づき、BT Metadata Collector の全機能を 6 ステップで実装した。

## 実装内容

### Step 1: プロジェクト基盤整備 (`feature/project-setup`)
- `.gitignore` — data/, .venv/, __pycache__ 等を除外
- `requirements.txt` — FastAPI, uvicorn, sse-starlette, jinja2, aiosqlite, dbus-python, PyGObject
- ディレクトリ構造 — app/, templates/, static/, data/, docs/dev-log/
- `__init__.py` ファイル

### Step 2: Raspberry Pi セットアップドキュメント (`feature/project-setup`)
- `docs/raspi-setup.md` — OS インストール、Bluetooth 設定、ペアリング手順、デプロイ手順、IP 固定設定
- 参考: https://sukiburo.jp/setup-raspberry-pi/

### Step 3: AVRCP モニター (`feature/avrcp-monitor`)
- `app/services/avrcp_monitor.py`
- D-Bus モード: BlueZ MediaPlayer1 の PropertiesChanged / InterfacesAdded シグナルを監視
- モックモード (`BT_MOCK=true`): 音楽/YouTube風/Podcast風/ラジオ風のテストデータを 5〜15 秒間隔で生成
- GLib メインループを別スレッドで実行し、`call_soon_threadsafe` で asyncio に橋渡し
- D-Bus 型 → Python ネイティブ型の変換関数を実装

### Step 4: FastAPI アプリ + セッション管理 (`feature/fastapi-app`)
- `app/main.py` — 全 9 エンドポイント実装
  - GET `/` — メインページ
  - POST `/session/start`, `/session/stop` — セッション制御
  - GET `/stream/metadata` — SSE リアルタイム配信
  - GET `/os-options` — 端末に応じた OS 選択肢の動的フィルタ
  - GET `/sessions`, `/sessions/{filename}` — 過去セッション一覧 + ダウンロード
  - GET `/health` — ヘルスチェック
- `app/services/database.py` — JSONL ファイル管理（保存、一覧取得、パストラバーサル対策付き）
- SSE は asyncio.Queue ベースで複数クライアントに配信

### Step 5: Web UI (`feature/web-ui`)
- Jinja2 テンプレート 7 ファイル（base, index, 5 partials）
- htmx + htmx-ext-sse による動的 UI
  - 端末選択 → OS 選択肢の動的切り替え
  - 「その他」選択時の自由入力フィールド切り替え
  - SSE でトラックカードをリアルタイム挿入（afterbegin）
  - セッション開始/終了でフォーム ↔ ステータス表示を切り替え
- ダークテーマ CSS（背景 #0f172a 系）、レスポンシブ対応
- トラックカードのスライドインアニメーション、録音中インジケーター

### Step 6: systemd サービス + README (`feature/systemd-readme`)
- `bt-metadata-collector.service` — systemd ユニットファイル
- `README.md` — 概要、セットアップリンク、起動方法、使い方

## ブランチ戦略

各ステップを個別のフィーチャーブランチで実装し、完了後に main へ順次マージした。

## 検証方法

```bash
BT_MOCK=true uvicorn app.main:app --host 0.0.0.0 --port 8000
```

ブラウザで `http://localhost:8000` にアクセスして動作確認。
