"""
データ分析・集計モジュール。

セッションデータを読み込み、メタデータ充実度マトリクスや
端末×OS比較テーブル、統計サマリーを生成する。
"""

import json
import logging
from collections import defaultdict
from pathlib import Path

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"

# 分析対象のメタデータフィールド
METADATA_FIELDS = [
    "title", "artist", "album", "genre",
    "track_number", "number_of_tracks", "duration_ms",
]


def _load_all_sessions() -> list[dict]:
    """全セッションデータを読み込む。ヘッダーとトラックを含む。"""
    if not DATA_DIR.exists():
        return []

    sessions = []
    for filepath in sorted(DATA_DIR.glob("*.jsonl")):
        try:
            header = None
            tracks = []
            with open(filepath, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    record = json.loads(line)
                    if record.get("type") == "session_header":
                        header = record
                    elif record.get("type") == "track":
                        tracks.append(record)

            if header:
                sessions.append({
                    "header": header,
                    "tracks": tracks,
                    "filename": filepath.name,
                })
        except (json.JSONDecodeError, OSError):
            logger.warning("セッションファイルの読み込みに失敗: %s", filepath.name)

    return sessions


def _has_value(value) -> bool:
    """メタデータフィールドに有意な値があるか判定する。"""
    if value is None:
        return False
    if isinstance(value, str) and not value.strip():
        return False
    if isinstance(value, (int, float)) and value == 0:
        return False
    return True


def get_statistics_summary() -> dict:
    """全体統計サマリーを返す。"""
    sessions = _load_all_sessions()

    total_sessions = len(sessions)
    total_tracks = sum(len(s["tracks"]) for s in sessions)

    # サービス別セッション数
    service_counts: dict[str, int] = defaultdict(int)
    for s in sessions:
        content = s["header"].get("content_name", "Unknown")
        service_counts[content] += 1

    # デバイス別セッション数
    device_counts: dict[str, int] = defaultdict(int)
    for s in sessions:
        device = s["header"].get("device", "Unknown")
        device_counts[device] += 1

    return {
        "total_sessions": total_sessions,
        "total_tracks": total_tracks,
        "service_counts": dict(sorted(service_counts.items(), key=lambda x: -x[1])),
        "device_counts": dict(sorted(device_counts.items(), key=lambda x: -x[1])),
    }


def get_field_coverage_matrix() -> dict:
    """メタデータ充実度マトリクスを返す。

    Returns:
        {
            "services": ["Spotify", "YouTube", ...],
            "fields": ["title", "artist", ...],
            "matrix": {
                "Spotify": {"title": 100.0, "artist": 95.0, ...},
                "YouTube": {"title": 80.0, ...},
            }
        }
    """
    sessions = _load_all_sessions()

    # サービスごとにトラックを集計
    service_tracks: dict[str, list[dict]] = defaultdict(list)
    for s in sessions:
        content = s["header"].get("content_name", "Unknown")
        service_tracks[content].extend(s["tracks"])

    matrix = {}
    for service, tracks in service_tracks.items():
        if not tracks:
            continue
        total = len(tracks)
        field_rates = {}
        for field_name in METADATA_FIELDS:
            count = sum(1 for t in tracks if _has_value(t.get(field_name)))
            field_rates[field_name] = round(count / total * 100, 1)
        matrix[service] = field_rates

    services = sorted(matrix.keys())

    return {
        "services": services,
        "fields": METADATA_FIELDS,
        "matrix": matrix,
    }


def get_device_os_comparison() -> list[dict]:
    """端末×OS比較テーブルデータを返す。

    Returns:
        [
            {
                "content_name": "Spotify",
                "device": "iPhone",
                "os_version": "iOS 18",
                "platform_type": "app",
                "session_count": 3,
                "track_count": 45,
                "field_coverage": {"title": 100.0, ...}
            },
            ...
        ]
    """
    sessions = _load_all_sessions()

    # (content, device, os, platform) ごとに集計
    groups: dict[tuple, dict] = {}
    for s in sessions:
        h = s["header"]
        key = (
            h.get("content_name", ""),
            h.get("device", ""),
            h.get("os_version", ""),
            h.get("platform_type", ""),
        )
        if key not in groups:
            groups[key] = {
                "content_name": key[0],
                "device": key[1],
                "os_version": key[2],
                "platform_type": key[3],
                "session_count": 0,
                "tracks": [],
            }
        groups[key]["session_count"] += 1
        groups[key]["tracks"].extend(s["tracks"])

    result = []
    for group in groups.values():
        tracks = group["tracks"]
        total = len(tracks) if tracks else 0
        field_coverage = {}
        for field_name in METADATA_FIELDS:
            if total > 0:
                count = sum(1 for t in tracks if _has_value(t.get(field_name)))
                field_coverage[field_name] = round(count / total * 100, 1)
            else:
                field_coverage[field_name] = 0.0

        result.append({
            "content_name": group["content_name"],
            "device": group["device"],
            "os_version": group["os_version"],
            "platform_type": group["platform_type"],
            "session_count": group["session_count"],
            "track_count": total,
            "field_coverage": field_coverage,
        })

    # content_name, device, os_version でソート
    result.sort(key=lambda x: (x["content_name"], x["device"], x["os_version"]))
    return result
