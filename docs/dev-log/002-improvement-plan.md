# 002: BT Metadata Collector 改善実装

## 実施日
2026-02-08

## 概要
初期実装完了後、実機での運用経験をもとに3つの方向性で改善を実施した。

---

## Phase 1: 運用の安定化（`feature/stable-ops`）

### 1-1. Bluetooth 自動 discoverable スクリプト
- **ファイル**: `scripts/bt-setup.sh`, `bt-agent.service`
- **意図**: RPi の電源 ON だけで Bluetooth が discoverable になり、SSH 不要でデバイスからペアリング可能にする
- **実装**: rfkill unblock → hciconfig up → bluetoothctl で discoverable/pairable 設定 → timeout 無制限
- `bt-agent.service` は oneshot + RemainAfterExit で起動時に1回だけ実行

### 1-2. systemd サービス改善
- **ファイル**: `bt-metadata-collector.service`
- `After=bt-agent.service` で BT セットアップ完了後に起動
- `Wants=bt-agent.service` で依存関係を明示（Requires ではなく Wants で柔軟に）
- `EnvironmentFile=-/home/pi/bt-metadata-collector/.env` で環境変数ファイル読み込み（`-` プレフィックスでファイル不在時もエラーにならない）
- `Restart=on-failure` + `RestartSec=3` で異常終了時に自動再起動

### 1-3. エラーログのファイル出力
- **ファイル**: `app/main.py`
- `RotatingFileHandler` を追加: `logs/app.log`（最大 5MB × 3 世代ローテーション）
- コンソール出力とファイル出力の両方にログを書き込む
- `.gitignore` に `logs/` を追加

### 1-4. ヘルスチェック強化
- **ファイル**: `app/main.py`（`/health` エンドポイント）
- 追加フィールド: `last_metadata_time`, `uptime_seconds`, `server_start_time`, `log_file_size_bytes`
- `_last_metadata_time` と `_server_start_time` のグローバル変数で時刻を追跡

---

## Phase 2: UX 改善（`feature/ux-improvement`）

### 2-1. セッション一覧の検索・フィルタ
- **ファイル**: `app/main.py`, `templates/partials/session_list.html`, `static/css/style.css`
- `GET /sessions` にクエリパラメータ（content, device, os_version）を追加
- htmx の `hx-trigger="change from:select, keyup changed delay:500ms from:input"` でフィルタ変更時に動的更新
- テキスト入力は 500ms のデバウンスで過剰なリクエストを防止

### 2-2. CSV エクスポート
- **ファイル**: `app/main.py`, `templates/partials/session_list.html`
- `GET /sessions/{filename}/csv` エンドポイントを新設
- JSONL の track レコードを csv.DictWriter で CSV に変換
- `Content-Disposition: attachment` ヘッダーでブラウザにダウンロードさせる
- セッション一覧テーブルに CSV ダウンロードリンク（DL）を追加

### 2-3. トラックカード Jinja2 テンプレート統一
- **ファイル**: `app/main.py`, `templates/partials/now_playing_card.html`
- `_render_track_card()` 内の文字列結合 HTML 生成を Jinja2 テンプレートレンダリングに置換
- `templates.get_template().render()` でテンプレート変数を渡す方式に変更
- テンプレート内で null 値の判定と `<span class="null-value">` の適用を実施

### 2-4. 未使用 aiosqlite 削除
- **ファイル**: `requirements.txt`
- `aiosqlite>=0.20` を削除（実際には JSONL ファイルベースのため不要だった）

---

## Phase 3-A: Web UI ダッシュボード（`feature/dashboard`）

### 分析ページの追加
- **ファイル**: `app/services/analysis.py`, `templates/dashboard.html`, `templates/partials/comparison_table.html`, `app/main.py`, `templates/base.html`, `static/css/style.css`

#### analysis.py
- `_load_all_sessions()`: data/ 内の全 JSONL を読み込みヘッダー+トラックのリストを返す
- `_has_value()`: メタデータフィールドに有意な値があるか判定（None, 空文字, 0 を除外）
- `get_statistics_summary()`: 総セッション数・トラック数・サービス別集計
- `get_field_coverage_matrix()`: サービス×フィールドの取得率マトリクス
- `get_device_os_comparison()`: (content, device, os, platform) ごとのクロス集計

#### ダッシュボード UI
- 統計サマリー: カード型の数値表示（総セッション数、総トラック数、サービス種類数、端末種類数）
- メタデータ充実度マトリクス: 色分け付きテーブル（緑=80%以上、黄=30-80%、赤=30%未満）
- 端末×OS 比較テーブル: 同じサービスでも端末/OS 別のフィールド取得率を確認

#### ナビゲーション
- `base.html` にヘッダーナビ（収集 / ダッシュボード）を追加

---

## Phase 3-B: Jupyter Notebook（`feature/analysis-notebook`）

### 分析ノートブック
- **ファイル**: `analysis/metadata_analysis.ipynb`, `analysis/requirements.txt`
- pandas, matplotlib, seaborn を使った詳細分析
- セクション構成:
  1. データ読み込み（JSONL → DataFrame）
  2. セッション情報結合
  3. メタデータ充実度ヒートマップ（seaborn heatmap）
  4. サービス×端末×OS クロス集計
  5. Duration 分布（箱ひげ図）
  6. まとめ

---

## ブランチ構成
| Phase | ブランチ | 状態 |
|-------|---------|------|
| Phase 1 | `feature/stable-ops` | push 済み |
| Phase 2 | `feature/ux-improvement` | push 済み（Phase 1 を含む） |
| Phase 3-A | `feature/dashboard` | push 済み（Phase 1+2 を含む） |
| Phase 3-B | `feature/analysis-notebook` | push 済み（main ベース） |
