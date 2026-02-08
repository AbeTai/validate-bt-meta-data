# app/services/ の初心者向け解説

## 概要

`app/services/` には2つのモジュールがある。

## avrcp_monitor.py — Bluetooth メタデータ監視

- Bluetooth AVRCP プロトコルで送られる曲情報（曲名、アーティスト名等）を監視
- 2つの動作モード:
  - **D-Bus モード（本番）**: Linux BlueZ の D-Bus シグナルを監視。PropertiesChanged と InterfacesAdded を購読
  - **モックモード（開発）**: `BT_MOCK=true` で有効。5〜15秒間隔でダミー曲データをランダム生成
- 重複排除: 2秒以内の同一トラック情報は無視
- ダミーデータのパターン: 通常音楽、YouTube風、Podcast風、ラジオ風
- `_dbus_to_python()`: D-Bus 型 → Python ネイティブ型の変換
- `_parse_track_metadata()`: キー名の正規化（Title → title）

## database.py — セッションログのファイル管理

- JSONL 形式で `data/` フォルダにセッションログを保存
- ファイル構造: 1行目がセッションヘッダー、2行目以降がトラックデータ
- `generate_filename()`: セッション情報からファイル名を自動生成（不正文字のサニタイズ付き）
- `save_session()`: セッションデータをJSONLに書き出し
- `list_sessions()`: data/ 内の .jsonl を新しい順に一覧取得
- `get_session_filepath()`: パストラバーサル対策付きのファイルパス取得

## 2つのモジュールの関係

- avrcp_monitor.py = データの「入口」（Bluetooth から取得）
- database.py = データの「出口」（ファイルに保存）
- main.py がこの2つを繋いでいる
