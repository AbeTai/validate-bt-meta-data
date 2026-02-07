"""
BT Metadata Collector — FastAPI アプリ本体。

Bluetooth AVRCP メタデータをリアルタイムに受信・記録する
Web アプリケーションのメインモジュール。
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, Form, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sse_starlette.sse import EventSourceResponse

from app.services.avrcp_monitor import AVRCPMonitor
from app.services.database import (
    generate_filename,
    get_session_filepath,
    list_sessions,
    save_session,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# OS 選択肢の定義
OS_OPTIONS: dict[str, list[str]] = {
    "iPhone": ["iOS 18", "iOS 17", "iOS 16"],
    "Mac": ["macOS Sequoia", "macOS Sonoma", "macOS Ventura"],
    "Windows": ["Windows 11", "Windows 10"],
    "Android": ["Android 15", "Android 14", "Android 13", "Android 12"],
}


@dataclass
class SessionState:
    """セッションの状態を管理するデータクラス。"""

    active: bool = False
    content_name: str = ""
    platform_type: str = ""
    device: str = ""
    os_version: str = ""
    start_time: Optional[datetime] = None
    tracks: list[dict] = field(default_factory=list)
    seq: int = 0


# グローバル状態
session = SessionState()
# SSE クライアントへの配信キュー
sse_queues: list[asyncio.Queue] = []
# asyncio イベントループ参照
_loop: Optional[asyncio.AbstractEventLoop] = None
# AVRCP モニター
_monitor: Optional[AVRCPMonitor] = None


def _on_metadata(metadata: dict):
    """AVRCP メタデータ受信コールバック（別スレッドから呼ばれる）。"""
    if _loop is None:
        return
    _loop.call_soon_threadsafe(_handle_metadata, metadata)


def _handle_metadata(metadata: dict):
    """メタデータを処理して SSE キューに配信する（asyncio スレッド）。"""
    if session.active:
        session.seq += 1
        track_record = {
            "type": "track",
            "seq": session.seq,
            "timestamp": metadata.get("timestamp", datetime.now().isoformat()),
            "title": metadata.get("title", ""),
            "artist": metadata.get("artist", ""),
            "album": metadata.get("album", ""),
            "genre": metadata.get("genre", ""),
            "track_number": metadata.get("track_number"),
            "number_of_tracks": metadata.get("number_of_tracks"),
            "duration_ms": metadata.get("duration_ms"),
            "status": metadata.get("status", ""),
        }
        session.tracks.append(track_record)

    # SSE で全クライアントに配信
    event_data = {
        "metadata": metadata,
        "track_count": session.seq if session.active else 0,
        "session_active": session.active,
    }
    for queue in sse_queues:
        try:
            queue.put_nowait(event_data)
        except asyncio.QueueFull:
            pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    """アプリケーションの起動・終了処理。"""
    global _loop, _monitor
    _loop = asyncio.get_event_loop()

    _monitor = AVRCPMonitor(callback=_on_metadata)
    _monitor.start()
    logger.info("アプリケーション起動完了 (mock=%s)", _monitor.is_mock)

    yield

    _monitor.stop()
    logger.info("アプリケーション終了")


app = FastAPI(title="BT Metadata Collector", lifespan=lifespan)

# 静的ファイルとテンプレート
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


# ── ページ ──


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """メインページ。"""
    sessions = list_sessions()
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "session": session,
            "sessions": sessions,
            "os_options": OS_OPTIONS,
        },
    )


# ── セッション管理 ──


@app.post("/session/start", response_class=HTMLResponse)
async def session_start(
    request: Request,
    content_name: str = Form(...),
    platform_type: str = Form(...),
    device: str = Form(...),
    os_version: str = Form(...),
):
    """セッションを開始する。"""
    session.active = True
    session.content_name = content_name
    session.platform_type = platform_type
    session.device = device
    session.os_version = os_version
    session.start_time = datetime.now()
    session.tracks = []
    session.seq = 0

    logger.info(
        "セッション開始: %s (%s, %s, %s)",
        content_name, platform_type, device, os_version,
    )

    return templates.TemplateResponse(
        "partials/session_status.html",
        {"request": request, "session": session},
    )


@app.post("/session/stop", response_class=HTMLResponse)
async def session_stop(request: Request):
    """セッションを終了してログを保存する。"""
    if not session.active:
        return templates.TemplateResponse(
            "partials/session_form.html",
            {"request": request, "session": session, "os_options": OS_OPTIONS},
        )

    session_end = datetime.now()

    # ログファイルに保存
    filename = generate_filename(
        session.content_name,
        session.platform_type,
        session.device,
        session.os_version,
        session.start_time,
    )

    save_session(
        filename=filename,
        content_name=session.content_name,
        platform_type=session.platform_type,
        device=session.device,
        os_version=session.os_version,
        session_start=session.start_time,
        session_end=session_end,
        tracks=session.tracks,
    )

    logger.info(
        "セッション終了: %s (%d トラック) -> %s",
        session.content_name, len(session.tracks), filename,
    )

    # セッション状態をリセット
    session.active = False
    session.tracks = []
    session.seq = 0

    sessions = list_sessions()

    return templates.TemplateResponse(
        "partials/session_form_and_list.html",
        {"request": request, "session": session, "sessions": sessions, "os_options": OS_OPTIONS},
    )


@app.get("/session/status", response_class=HTMLResponse)
async def session_status(request: Request):
    """現在のセッション状態を返す。"""
    if session.active:
        return templates.TemplateResponse(
            "partials/session_status.html",
            {"request": request, "session": session},
        )
    return templates.TemplateResponse(
        "partials/session_form.html",
        {"request": request, "session": session, "os_options": OS_OPTIONS},
    )


# ── OS 選択肢 ──


@app.get("/os-options", response_class=HTMLResponse)
async def os_options(device: str = Query("")):
    """端末に応じた OS 選択肢を返す。"""
    options = OS_OPTIONS.get(device, [])
    html = '<option value="">-- 選択 --</option>\n'
    for opt in options:
        html += f'<option value="{opt}">{opt}</option>\n'
    html += '<option value="その他">その他（自由入力）</option>\n'
    return HTMLResponse(content=html)


# ── SSE ──


@app.get("/stream/metadata")
async def stream_metadata(request: Request):
    """SSE でメタデータをリアルタイム配信する。"""
    queue: asyncio.Queue = asyncio.Queue(maxsize=100)
    sse_queues.append(queue)

    async def event_generator():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    data = await asyncio.wait_for(queue.get(), timeout=30)
                    metadata = data["metadata"]

                    # トラックカード HTML を生成
                    card_html = _render_track_card(
                        metadata, data["session_active"], data["track_count"]
                    )
                    yield {
                        "event": "metadata",
                        "data": card_html,
                    }

                    # トラック数更新
                    if data["session_active"]:
                        yield {
                            "event": "track-count",
                            "data": str(data["track_count"]),
                        }

                except asyncio.TimeoutError:
                    # キープアライブ
                    yield {"event": "ping", "data": ""}

        finally:
            sse_queues.remove(queue)

    return EventSourceResponse(event_generator())


def _format_duration(duration_ms) -> str:
    """ミリ秒を M:SS または H:MM:SS 形式に変換する。"""
    if not duration_ms or duration_ms <= 0:
        return "--:--"
    total_seconds = duration_ms // 1000
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    if hours > 0:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


def _render_track_card(metadata: dict, session_active: bool, track_count: int) -> str:
    """トラックカードの HTML を生成する。"""
    timestamp = metadata.get("timestamp", "")
    try:
        dt = datetime.fromisoformat(timestamp)
        time_str = dt.strftime("%H:%M:%S")
    except (ValueError, TypeError):
        time_str = timestamp

    title = metadata.get("title") or None
    artist = metadata.get("artist") or None
    album = metadata.get("album") or None
    genre = metadata.get("genre") or None
    duration_ms = metadata.get("duration_ms")
    track_number = metadata.get("track_number")
    number_of_tracks = metadata.get("number_of_tracks")
    status = metadata.get("status") or None

    duration_str = _format_duration(duration_ms) if duration_ms else "null"

    # 表示値（null 表示対応）
    title_display = title if title else "null"
    artist_display = artist if artist else "null"
    album_display = album if album else "null"
    genre_display = genre if genre else "null"
    track_num_display = str(track_number) if track_number is not None else "null"
    num_tracks_display = str(number_of_tracks) if number_of_tracks is not None else "null"
    status_display = status if status else "null"

    # ステータスの色
    status_class = {
        "playing": "status-playing",
        "paused": "status-paused",
        "stopped": "status-stopped",
    }.get(status or "", "")

    # null 表示用の CSS クラス
    def _val(display_value):
        if display_value == "null":
            return f'<span class="null-value">null</span>'
        return display_value

    # 録音中インジケーター
    recording = "recording" if session_active else ""

    # HTML 生成
    parts = [
        f'<div class="track-card {recording}">',
        f'  <div class="track-header">',
        f'    <span class="track-time">{time_str}</span>',
        f'    <span class="track-status {status_class}">{_val(status_display)}</span>',
        f'  </div>',
        f'  <div class="track-field"><span class="label">Title:</span> {_val(title_display)}</div>',
        f'  <div class="track-field"><span class="label">Artist:</span> {_val(artist_display)}</div>',
        f'  <div class="track-field"><span class="label">Album:</span> {_val(album_display)}</div>',
        f'  <div class="track-field"><span class="label">Genre:</span> {_val(genre_display)}</div>',
        f'  <div class="track-field"><span class="label">TrackNumber:</span> {_val(track_num_display)}</div>',
        f'  <div class="track-field"><span class="label">NumberOfTracks:</span> {_val(num_tracks_display)}</div>',
        f'  <div class="track-field"><span class="label">Duration:</span> {_val(duration_str)}</div>',
        f'</div>',
    ]

    return "\n".join(parts)


# ── 過去セッション ──


@app.get("/sessions", response_class=HTMLResponse)
async def get_sessions(request: Request):
    """過去セッション一覧を返す。"""
    sessions = list_sessions()
    return templates.TemplateResponse(
        "partials/session_list.html",
        {"request": request, "sessions": sessions},
    )


@app.get("/sessions/{filename}")
async def download_session(filename: str):
    """セッションログファイルをダウンロードする。"""
    filepath = get_session_filepath(filename)
    if filepath is None:
        return JSONResponse(
            status_code=404,
            content={"detail": "ファイルが見つかりません"},
        )
    return FileResponse(
        path=filepath,
        filename=filename,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── ヘルスチェック ──


@app.get("/health")
async def health():
    """ヘルスチェック。"""
    return {
        "status": "ok",
        "session_active": session.active,
        "mock_mode": _monitor.is_mock if _monitor else None,
    }
