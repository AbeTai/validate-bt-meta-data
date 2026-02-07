# BT Metadata Collector — 実装仕様書

## 1. プロジェクト概要

Bluetooth AVRCP メタデータをリアルタイムに受信・記録するツール。
Raspberry Pi を Bluetooth オーディオレシーバー（A2DP Sink）として動作させ、各種デバイス（iPhone / Mac / Windows / Android）から送信されるメタデータ（曲名、アーティスト名、アルバム名等）を収集する。

**記録用端末（ローカル Mac）** のブラウザから Web UI を操作し、セッション単位でメタデータを記録・保存する。

---

## 2. システム構成

```
┌─────────────────────┐     Bluetooth (A2DP + AVRCP)     ┌─────────────────────┐
│  コンテンツ再生端末  │ ──────────────────────────────► │   Raspberry Pi 4    │
│  (iPhone/Mac/Win/    │                                  │   (A2DP Sink)       │
│   Android)           │                                  │                     │
└─────────────────────┘                                  │  BlueZ + D-Bus      │
                                                          │  FastAPI サーバー    │
                                                          │  :8000              │
                                                          └──────────┬──────────┘
                                                                     │ Wi-Fi / LAN
                                                          ┌──────────▼──────────┐
                                                          │  記録用端末          │
                                                          │  (ローカル Mac)      │
                                                          │  ブラウザで操作      │
                                                          └─────────────────────┘
```

### ハードウェア

| 役割 | デバイス | 備考 |
|---|---|---|
| AVRCP レシーバー + サーバー | Raspberry Pi 4 Model B (2GB) | Bluetooth 5.0 内蔵。OS未セットアップ |
| 記録用端末 | Mac（ローカル） | ブラウザで `http://<RPi IP>:8000` にアクセス |
| コンテンツ再生端末 | iPhone / Mac / Windows PC / Android | テスト対象。RPi と BT ペアリングして音楽・動画を再生 |

---

## 3. Raspberry Pi 初期セットアップ手順

この手順を `docs/raspi-setup.md` として同梱し、README から参照する。

### 3.1 OS インストール

1. 別の Mac/PC で **Raspberry Pi Imager** をダウンロード（https://www.raspberrypi.com/software/）
2. microSD カード（16GB 以上推奨）を挿入
3. Imager で以下を設定:
   - OS: **Raspberry Pi OS (64-bit) Bookworm** — Desktop なし（Lite）で十分
   - 歯車アイコン（詳細設定）で以下を入力:
     - ホスト名: `bt-collector`（任意）
     - SSH を有効化: パスワード認証
     - ユーザー名 / パスワード: 任意（例: `pi` / 任意パスワード）
     - Wi-Fi: SSID とパスワードを入力（記録用 Mac と同じネットワーク）
     - ロケール: Asia/Tokyo, JP キーボード
4. 書き込み → microSD を RPi に挿入 → 電源投入
5. Mac から SSH 接続: `ssh pi@bt-collector.local`

### 3.2 システム更新と依存パッケージ

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y \
    bluez \
    python3-venv python3-dev python3-dbus python3-gi \
    libdbus-1-dev libglib2.0-dev pkg-config gcc \
    git
```

> **注意**: PipeWire / PulseAudio は不要。本ツールはオーディオ再生せず、AVRCP メタデータのみを取得する。A2DP Sink プロファイルの登録は BlueZ が自動で行う。

### 3.3 Bluetooth 設定

`/etc/bluetooth/main.conf` に以下を追記:

```ini
[General]
Name = BT-MetadataCollector
Class = 0x20041C
DiscoverableTimeout = 0
AlwaysPairable = true
JustWorksRepairing = always
```

```bash
sudo systemctl restart bluetooth
```

### 3.4 ペアリング手順（端末ごと）

```bash
bluetoothctl
> discoverable on
> pairable on
> agent on
> default-agent
```

コンテンツ再生端末の Bluetooth 設定から「BT-MetadataCollector」を検出してペアリング。
ペアリング完了後、`bluetoothctl` で `trust <MAC>` を実行して自動再接続を有効化。

```bash
> trust XX:XX:XX:XX:XX:XX
> exit
```

**全対象端末（iPhone / Mac / Windows / Android）で上記を実施する。**

### 3.5 アプリケーションのデプロイ

```bash
cd ~
git clone <リポジトリURL> bt-metadata-collector
cd bt-metadata-collector
python3 -m venv .venv --system-site-packages
source .venv/bin/activate
pip install -r requirements.txt
mkdir -p data
```

### 3.6 systemd サービス登録

```bash
sudo cp bt-metadata-collector.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable bt-metadata-collector
sudo systemctl start bt-metadata-collector
```

---

## 4. アプリケーション仕様

### 4.1 技術スタック

| 層 | 技術 | バージョン |
|---|---|---|
| 言語 | Python | 3.11+（Bookworm 標準） |
| Web フレームワーク | FastAPI | >= 0.115 |
| テンプレート | Jinja2 | >= 3.1 |
| リアルタイム通信 | SSE (sse-starlette) | >= 2.0 |
| フロントエンド | htmx + htmx-ext-sse | 2.0.4 / 2.2.2 |
| Bluetooth | BlueZ D-Bus API (dbus-python + PyGObject) | |
| DB | SQLite (aiosqlite) | |
| CSS | カスタム（フレームワークなし） | ダークテーマ |

### 4.2 プロジェクト構造

```
bt-metadata-collector/
├── app/
│   ├── __init__.py
│   ├── main.py                     # FastAPI アプリ本体
│   └── services/
│       ├── __init__.py
│       ├── avrcp_monitor.py        # BlueZ D-Bus AVRCP 監視
│       └── database.py             # SQLite ストレージ
├── templates/
│   ├── base.html                   # ベーステンプレート
│   ├── index.html                  # メインページ（セッション管理 + モニター）
│   └── partials/
│       ├── session_form.html       # セッション開始フォーム
│       ├── now_playing_card.html   # トラックカード（SSE で配信）
│       ├── session_status.html     # セッション状態表示
│       └── session_list.html       # 過去セッション一覧
├── static/
│   └── css/
│       └── style.css
├── data/                           # ログ保存先（.jsonl）※ gitignore
├── docs/
│   └── raspi-setup.md
├── bt-metadata-collector.service   # systemd ユニットファイル
├── requirements.txt
├── README.md
└── .gitignore
```

---

## 5. 画面設計

### 5.1 画面構成（単一ページ）

全機能を **1 ページ** に収める。上から順に:

1. **セッション制御エリア**（上部固定）
2. **リアルタイムメタデータフィード**（中央、SSE で自動更新）
3. **過去セッション一覧**（下部）

### 5.2 セッション制御エリア

#### セッション未開始時: 入力フォームを表示

| フィールド | 種類 | 選択肢 / 制約 | 必須 |
|---|---|---|---|
| コンテンツ名 | テキスト入力 | 自由入力。例: "Spotify", "YouTube", "Apple Music", "Netflix", "radiko" | ✅ |
| Web or アプリ | セレクト | `web` / `app` | ✅ |
| コンテンツ再生端末 | セレクト | `iPhone` / `Mac` / `Windows` / `Android` | ✅ |
| コンテンツ再生 OS | セレクト | `iOS 18` / `iOS 17` / `macOS Sequoia` / `macOS Sonoma` / `Windows 11` / `Windows 10` / `Android 15` / `Android 14` / `Android 13` / `その他`（自由入力に切替） | ✅ |

**フォーム下部に「セッション開始」ボタン。**

> **UI の挙動**: 「コンテンツ再生端末」の選択に応じて「コンテンツ再生 OS」の選択肢を動的にフィルタリングする（htmx で実装）。
> - iPhone → iOS 18, iOS 17
> - Mac → macOS Sequoia, macOS Sonoma
> - Windows → Windows 11, Windows 10
> - Android → Android 15, Android 14, Android 13

#### セッション進行中: ステータス表示 + 終了ボタン

- 入力済み情報のサマリー表示（編集不可）
- セッション開始時刻
- 受信トラック数（リアルタイム更新）
- **「セッション終了 → ログ保存」ボタン**（赤系、目立つ配置）

### 5.3 リアルタイムメタデータフィード

SSE (`/stream/metadata`) で AVRCP メタデータ変更をプッシュ。新しいトラックが上に追加される（`afterbegin`）。

各トラックカードに表示する情報:

| フィールド | 表示 |
|---|---|
| 受信時刻 | `HH:MM:SS` 形式 |
| Title | 曲名。空なら `(タイトルなし)` |
| Artist | アーティスト名。空なら `(不明)` |
| Album | アルバム名。空なら非表示 |
| Genre | ジャンル。空なら非表示 |
| Duration | `M:SS` or `H:MM:SS` 形式。0 なら `--:--` |
| TrackNumber | `#N` or `#N/Total` 形式。0 なら非表示 |
| Status | `playing` / `paused` / `stopped`。色分け表示 |

**セッション未開始の場合**: フィードは表示するが、ログには記録しない。「セッションを開始してください」のメッセージを表示。

### 5.4 過去セッション一覧

保存済みのセッションファイル（`data/` ディレクトリ内の `.jsonl` ファイル）を一覧表示。

| 列 | 内容 |
|---|---|
| ファイル名 | リンク（クリックでダウンロード） |
| コンテンツ名 | |
| Web/アプリ | |
| 端末 | |
| OS | |
| トラック数 | |
| 記録時間 | |

---

## 6. セッションの処理フロー

### 6.1 セッション開始

```
POST /session/start
Body: content_name, platform_type, device, os_version
```

1. サーバー側で `SessionState` を生成（開始時刻、入力情報を保持）
2. `session_active = True` に設定
3. 以降の AVRCP メタデータ受信イベントをメモリ上のリストに蓄積開始
4. htmx でフォームをステータス表示に差し替え

### 6.2 メタデータ受信（セッション進行中）

```
BlueZ D-Bus signal → AVRCPMonitor → callback → FastAPI
```

1. `avrcp_monitor.py` の `on_track_update` コールバックが発火
2. `session_active` なら、メタデータをセッションのトラックリストに追加
3. SSE で全クライアントにトラックカード HTML を配信
4. トラック数カウンターを更新（SSE で配信）

### 6.3 セッション終了 → ログ保存

```
POST /session/stop
```

1. `session_active = False` に設定
2. セッション中に蓄積したメタデータを JSONL ファイルに書き出す
3. ファイル名は入力情報から自動生成（後述）
4. メモリ上のトラックリストをクリア
5. htmx でステータス表示をフォームに戻す
6. 過去セッション一覧を更新

---

## 7. ログファイル仕様

### 7.1 ファイル名

```
{YYYYMMDD}_{HHmmss}_{content_name}_{platform_type}_{device}_{os_version}.jsonl
```

例:
```
20260207_143208_Spotify_app_iPhone_iOS18.jsonl
20260207_150012_YouTube_web_Mac_macOSSequoia.jsonl
20260207_160530_Netflix_app_Android_Android15.jsonl
```

**ファイル名のサニタイズルール**:
- スペース → `_`（アンダースコア）
- 英数字・ハイフン・アンダースコア・ドット以外の文字を削除
- 最大 200 文字で切り詰め

### 7.2 ファイル形式: JSONL

1 行 = 1 レコード。先頭行はセッションメタ情報、2 行目以降はトラックデータ。

**1 行目: セッションヘッダー**

```json
{"type": "session_header", "content_name": "Spotify", "platform_type": "app", "device": "iPhone", "os_version": "iOS 18", "session_start": "2026-02-07T14:32:08.123456", "session_end": "2026-02-07T14:45:30.654321", "track_count": 5}
```

**2 行目以降: トラックデータ**

```json
{"type": "track", "seq": 1, "timestamp": "2026-02-07T14:32:15.789012", "title": "Bohemian Rhapsody", "artist": "Queen", "album": "A Night at the Opera", "genre": "Rock", "track_number": 11, "number_of_tracks": 12, "duration_ms": 354000, "status": "playing"}
{"type": "track", "seq": 2, "timestamp": "2026-02-07T14:38:10.456789", "title": "Blinding Lights", "artist": "The Weeknd", "album": "After Hours", "genre": "Synth-pop", "track_number": 9, "number_of_tracks": 14, "duration_ms": 200000, "status": "playing"}
```

**フィールド定義（トラックデータ）**:

| フィールド | 型 | 説明 |
|---|---|---|
| type | string | 固定値 `"track"` |
| seq | int | セッション内の連番（1 始まり） |
| timestamp | string | ISO 8601 形式。メタデータ受信時刻 |
| title | string | AVRCP Title 属性。空文字列の場合あり |
| artist | string | AVRCP Artist 属性。空文字列の場合あり |
| album | string | AVRCP Album 属性。空文字列の場合あり |
| genre | string | AVRCP Genre 属性。空文字列の場合あり |
| track_number | int or null | AVRCP TrackNumber 属性 |
| number_of_tracks | int or null | AVRCP NumberOfTracks 属性 |
| duration_ms | int or null | AVRCP Duration 属性（ミリ秒） |
| status | string | `"playing"` / `"paused"` / `"stopped"` / `""` |

### 7.3 保存先

```
data/
├── 20260207_143208_Spotify_app_iPhone_iOS18.jsonl
├── 20260207_150012_YouTube_web_Mac_macOSSequoia.jsonl
└── ...
```

---

## 8. API エンドポイント一覧

| メソッド | パス | 説明 | レスポンス |
|---|---|---|---|
| GET | `/` | メインページ | HTML |
| GET | `/stream/metadata` | SSE: メタデータリアルタイム配信 | SSE (text/event-stream) |
| POST | `/session/start` | セッション開始 | HTML partial (session_status) |
| POST | `/session/stop` | セッション終了 → ログ保存 | HTML partial (session_form + session_list) |
| GET | `/session/status` | 現在のセッション状態 | HTML partial |
| GET | `/os-options` | OS 選択肢を動的に返す | HTML partial (`<option>` タグ) |
| GET | `/sessions` | 過去セッション一覧 | HTML partial (session_list) |
| GET | `/sessions/{filename}` | ログファイルダウンロード | application/x-ndjson |
| GET | `/health` | ヘルスチェック | JSON |

---

## 9. AVRCP モニター仕様 (`avrcp_monitor.py`)

### 9.1 概要

BlueZ の D-Bus API (`org.bluez.MediaPlayer1`) を監視し、メタデータ変更を検出してコールバックを発火する。

### 9.2 監視対象シグナル

| シグナル | インターフェース | 用途 |
|---|---|---|
| `PropertiesChanged` | `org.freedesktop.DBus.Properties` | `Track` / `Status` プロパティの変更検出 |
| `InterfacesAdded` | `org.freedesktop.DBus.ObjectManager` | 新規 BT デバイス接続の検出 |

### 9.3 D-Bus → Python 型変換

D-Bus 型（`dbus.String`, `dbus.Int32` 等）は全て Python ネイティブ型に変換してからコールバックに渡す。

### 9.4 モックモード

環境変数 `BT_MOCK=true` の場合、D-Bus を使わずモックデータを定期的に生成する。開発・テスト用。モック間隔は 5〜15 秒のランダム。

モックデータには以下のパターンを含める:
- 通常の音楽（全フィールド充実）
- YouTube 風（Album 空、Duration 0）
- Podcast 風（Duration が長い、Genre が "Podcast"）
- ラジオ風（情報が最小限）

### 9.5 GLib メインループ

D-Bus シグナルの受信には GLib メインループが必要。**別スレッド**で `GLib.MainLoop().run()` を実行し、コールバック内で `asyncio.loop.call_soon_threadsafe()` を使って FastAPI の asyncio イベントループにイベントを渡す。

---

## 10. 非機能要件

### 10.1 パフォーマンス

- AVRCP メタデータ受信から Web UI 表示まで **1 秒以内**
- 同時接続クライアント: 最大 5（家庭内 LAN 想定）
- セッションあたりのトラック数上限: なし（メモリに蓄積、1000 トラック程度は問題なし）

### 10.2 エラーハンドリング

- BT 接続断: ログにワーニング出力。セッションは継続（再接続時に自動復帰）
- D-Bus エラー: モックモードにフォールバック（初回起動時のみ判定）
- ファイル書き込みエラー: セッション終了 API でエラーレスポンスを返す

### 10.3 状態管理

- セッション状態はサーバーのメモリ上で管理（シングルプロセス前提）
- 同時に実行可能なセッションは **1 つのみ**
- サーバー再起動時、進行中セッションは失われる（許容）

---

## 11. OS 選択肢の動的フィルタリング

`GET /os-options?device={device}` で `<option>` タグを返す。htmx で端末セレクト変更時に OS セレクトを差し替える。

```python
OS_OPTIONS = {
    "iPhone": ["iOS 18", "iOS 17", "iOS 16"],
    "Mac": ["macOS Sequoia", "macOS Sonoma", "macOS Ventura"],
    "Windows": ["Windows 11", "Windows 10"],
    "Android": ["Android 15", "Android 14", "Android 13", "Android 12"],
}
```

HTML:
```html
<select name="device"
        hx-get="/os-options"
        hx-target="#os-select"
        hx-swap="innerHTML"
        hx-include="this">
    <option value="">-- 選択 --</option>
    <option value="iPhone">iPhone</option>
    <option value="Mac">Mac</option>
    <option value="Windows">Windows</option>
    <option value="Android">Android</option>
</select>

<select name="os_version" id="os-select">
    <option value="">-- 端末を先に選択 --</option>
</select>
```

---

## 12. systemd サービスファイル

`bt-metadata-collector.service`:

```ini
[Unit]
Description=BT Metadata Collector
After=bluetooth.target network.target
Requires=bluetooth.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/bt-metadata-collector
Environment=PATH=/home/pi/bt-metadata-collector/.venv/bin:/usr/bin:/bin
Environment=BT_MOCK=false
ExecStart=/home/pi/bt-metadata-collector/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

---

## 13. 開発時の注意事項（Claude Code 向け）

### 13.1 D-Bus 関連

- `dbus-python` と `PyGObject` は `--system-site-packages` で venv に引き込む。pip でのインストールはビルドに C コンパイラと `libdbus-1-dev`, `libglib2.0-dev` が必要
- D-Bus のメインループは **別スレッド** で実行すること。FastAPI の asyncio ループをブロックしてはならない
- `dbus.Dictionary`, `dbus.String` 等の D-Bus 型は JSON シリアライズ不可。必ず Python ネイティブ型に変換する

### 13.2 htmx + SSE

- htmx の SSE 拡張 (`htmx-ext-sse`) を使用。CDN から読み込む
- SSE エンドポイントは `sse-starlette` の `EventSourceResponse` を使用
- SSE イベントのデータは **HTML 断片**（JSON ではない）
- htmx の `sse-swap` 属性でイベント名に応じた DOM 更新を行う

### 13.3 ファイル I/O

- JSONL 書き出しは `json.dumps(..., ensure_ascii=False)` を使用（日本語対応）
- ファイル名のサニタイズは `re.sub(r'[^\w\-.]', '', name.replace(' ', '_'))` 程度で十分

### 13.4 テスト

- モックモード (`BT_MOCK=true`) で Web UI の動作確認が可能
- 実機テストは Raspberry Pi + BT イヤホン or スマホで行う

### 13.5 CSS

- ダークテーマ（背景 `#0f172a` 系）
- フレームワーク不使用。カスタム CSS のみ
- レスポンシブ対応（Mac ブラウザで使うため最低限でよい）

---

## 14. 実装の優先順位

1. **Raspberry Pi セットアップドキュメント** (`docs/raspi-setup.md`)
2. **AVRCP モニター** (`avrcp_monitor.py`) — D-Bus 監視 + モックモード
3. **FastAPI アプリ骨格** (`main.py`) — ルーティング、SSE、セッション管理
4. **Web UI** — テンプレート + CSS
5. **ログ保存** — JSONL 書き出し + ファイル名生成
6. **systemd サービス** + README

---

## 15. 備考: AVRCP の技術的制約

- AVRCP 標準メタデータには **ソースアプリの識別子が存在しない**。Title / Artist / Album / Genre / TrackNumber / NumberOfTracks / Duration の 7 フィールドのみ
- そのため「どのサービスで再生しているか」は AVRCP メタデータからは判定できない。本ツールでは Web UI のセッション入力で人間が指定する設計
- 同一サービスでも OS によってメタデータの充実度が異なる場合がある（例: Android の YouTube は Album を空にすることが多い）。これがまさに本ツールで調査したいポイント