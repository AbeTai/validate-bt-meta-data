# 003: セッション削除機能の追加

## 実施日
2026-02-08

## 概要
セッション一覧からログデータ（JSONL ファイル）を削除できる機能を追加した。

## 変更内容

### `app/services/database.py`
- `delete_session(filename)` 関数を追加
- `get_session_filepath()` でパストラバーサル対策済みのパスを取得し、`unlink()` で削除

### `app/main.py`
- `DELETE /sessions/{filename}` エンドポイントを追加
- 削除後にセッション一覧を再レンダリングして返す（htmx で動的更新）

### `templates/partials/session_list.html`
- 各行に `x` ボタンを追加
- `hx-delete` で DELETE リクエストを送信
- `hx-confirm` でブラウザの確認ダイアログを表示し、誤削除を防止

### `static/css/style.css`
- `.btn-delete` スタイルを追加（赤枠、ホバー時に赤背景に変化）
