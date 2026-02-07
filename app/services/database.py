"""
セッションログのファイル管理モジュール。

セッションデータを JSONL 形式でファイルに書き出し、
過去セッション一覧の取得やファイルダウンロードを提供する。
"""

import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"


def _sanitize_filename(name: str) -> str:
    """ファイル名に使えない文字を除去する。"""
    name = name.replace(" ", "_")
    name = re.sub(r"[^\w\-.]", "", name)
    return name[:200]


def generate_filename(
    content_name: str,
    platform_type: str,
    device: str,
    os_version: str,
    session_start: datetime,
) -> str:
    """セッション情報からログファイル名を生成する。"""
    timestamp = session_start.strftime("%Y%m%d_%H%M%S")
    parts = [
        timestamp,
        _sanitize_filename(content_name),
        _sanitize_filename(platform_type),
        _sanitize_filename(device),
        _sanitize_filename(os_version),
    ]
    return "_".join(parts) + ".jsonl"


def save_session(
    filename: str,
    content_name: str,
    platform_type: str,
    device: str,
    os_version: str,
    session_start: datetime,
    session_end: datetime,
    tracks: list[dict],
) -> Path:
    """セッションデータを JSONL ファイルに保存する。"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    filepath = DATA_DIR / filename

    with open(filepath, "w", encoding="utf-8") as f:
        # 1行目: セッションヘッダー
        header = {
            "type": "session_header",
            "content_name": content_name,
            "platform_type": platform_type,
            "device": device,
            "os_version": os_version,
            "session_start": session_start.isoformat(),
            "session_end": session_end.isoformat(),
            "track_count": len(tracks),
        }
        f.write(json.dumps(header, ensure_ascii=False) + "\n")

        # 2行目以降: トラックデータ
        for track in tracks:
            f.write(json.dumps(track, ensure_ascii=False) + "\n")

    logger.info("セッションログを保存: %s (%d トラック)", filename, len(tracks))
    return filepath


def list_sessions() -> list[dict]:
    """過去セッション一覧を取得する。"""
    if not DATA_DIR.exists():
        return []

    sessions = []
    for filepath in sorted(DATA_DIR.glob("*.jsonl"), reverse=True):
        session_info = _read_session_header(filepath)
        if session_info:
            session_info["filename"] = filepath.name
            sessions.append(session_info)

    return sessions


def _read_session_header(filepath: Path) -> Optional[dict]:
    """JSONL ファイルの先頭行（セッションヘッダー）を読み取る。"""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            first_line = f.readline().strip()
            if not first_line:
                return None
            data = json.loads(first_line)
            if data.get("type") == "session_header":
                return data
    except (json.JSONDecodeError, OSError):
        logger.warning("セッションヘッダーの読み取りに失敗: %s", filepath.name)
    return None


def get_session_filepath(filename: str) -> Optional[Path]:
    """ファイル名からセッションファイルのパスを取得する。"""
    # パストラバーサル対策
    if "/" in filename or "\\" in filename or ".." in filename:
        return None

    filepath = DATA_DIR / filename
    if filepath.exists() and filepath.suffix == ".jsonl":
        return filepath
    return None
