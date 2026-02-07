"""
BlueZ D-Bus AVRCP メタデータ監視モジュール。

D-Bus 経由で BlueZ の MediaPlayer1 インターフェースを監視し、
AVRCP メタデータの変更をコールバックで通知する。

環境変数 BT_MOCK=true でモックモードが有効になり、
D-Bus を使わずにテストデータを定期的に生成する。
"""

import logging
import os
import random
import threading
import time
from datetime import datetime
from typing import Callable, Optional

logger = logging.getLogger(__name__)

# AVRCP メタデータのコールバック型
# callback(metadata: dict) の形式で呼び出される
MetadataCallback = Callable[[dict], None]


def _dbus_to_python(value):
    """D-Bus 型を Python ネイティブ型に変換する。"""
    try:
        import dbus
    except ImportError:
        return value

    if isinstance(value, dbus.String):
        return str(value)
    elif isinstance(value, (dbus.Int16, dbus.Int32, dbus.Int64,
                            dbus.UInt16, dbus.UInt32, dbus.UInt64)):
        return int(value)
    elif isinstance(value, dbus.Double):
        return float(value)
    elif isinstance(value, dbus.Boolean):
        return bool(value)
    elif isinstance(value, dbus.Array):
        return [_dbus_to_python(item) for item in value]
    elif isinstance(value, dbus.Dictionary):
        return {_dbus_to_python(k): _dbus_to_python(v) for k, v in value.items()}
    elif isinstance(value, dbus.Byte):
        return int(value)
    else:
        return value


def _parse_track_metadata(track_dict: dict) -> dict:
    """AVRCP Track メタデータ辞書を正規化する。"""
    return {
        "title": track_dict.get("Title", ""),
        "artist": track_dict.get("Artist", ""),
        "album": track_dict.get("Album", ""),
        "genre": track_dict.get("Genre", ""),
        "track_number": track_dict.get("TrackNumber"),
        "number_of_tracks": track_dict.get("NumberOfTracks"),
        "duration_ms": track_dict.get("Duration"),
    }


class AVRCPMonitor:
    """BlueZ D-Bus AVRCP メタデータモニター。"""

    def __init__(self, callback: MetadataCallback):
        self._callback = callback
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._mock_mode = os.environ.get("BT_MOCK", "").lower() == "true"
        self._current_status = ""
        self._last_track_key = ""
        self._last_track_time = 0.0

    @property
    def is_mock(self) -> bool:
        return self._mock_mode

    def start(self):
        """モニターを開始する。別スレッドで実行。"""
        if self._running:
            return

        self._running = True

        if self._mock_mode:
            logger.info("モックモードで AVRCP モニターを開始")
            self._thread = threading.Thread(
                target=self._mock_loop, daemon=True, name="avrcp-mock"
            )
        else:
            logger.info("D-Bus モードで AVRCP モニターを開始")
            self._thread = threading.Thread(
                target=self._dbus_loop, daemon=True, name="avrcp-dbus"
            )

        self._thread.start()

    def stop(self):
        """モニターを停止する。"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None
            logger.info("AVRCP モニターを停止")

    def _dbus_loop(self):
        """D-Bus メインループを実行する（別スレッド）。"""
        try:
            import dbus
            from dbus.mainloop.glib import DBusGMainLoop
            from gi.repository import GLib

            DBusGMainLoop(set_as_default=True)
            bus = dbus.SystemBus()

            # PropertiesChanged シグナルを監視
            bus.add_signal_receiver(
                self._on_properties_changed,
                dbus_interface="org.freedesktop.DBus.Properties",
                signal_name="PropertiesChanged",
                path_keyword="path",
            )

            # InterfacesAdded シグナルを監視（新規デバイス接続検出）
            bus.add_signal_receiver(
                self._on_interfaces_added,
                dbus_interface="org.freedesktop.DBus.ObjectManager",
                signal_name="InterfacesAdded",
            )

            logger.info("D-Bus シグナル監視を開始")
            loop = GLib.MainLoop()

            while self._running:
                context = loop.get_context()
                context.iteration(True)

        except ImportError:
            logger.error(
                "dbus-python または PyGObject が見つかりません。"
                "モックモード (BT_MOCK=true) で起動してください。"
            )
            self._mock_mode = True
            self._mock_loop()
        except Exception:
            logger.exception("D-Bus ループでエラーが発生")

    def _on_properties_changed(self, interface, changed, invalidated, path=""):
        """D-Bus PropertiesChanged シグナルのハンドラー。"""
        if interface != "org.bluez.MediaPlayer1":
            return

        changed = _dbus_to_python(changed)

        metadata = {}

        if "Track" in changed:
            metadata = _parse_track_metadata(changed["Track"])

        if "Status" in changed:
            self._current_status = changed["Status"]

        if metadata:
            # 同一トラックの重複シグナルを除外（2秒以内の同じ Title+Artist）
            track_key = f"{metadata.get('title', '')}|{metadata.get('artist', '')}"
            now = time.time()
            if track_key == self._last_track_key and (now - self._last_track_time) < 2.0:
                logger.debug("重複シグナルをスキップ: %s", metadata.get("title", ""))
                return
            self._last_track_key = track_key
            self._last_track_time = now

            metadata["status"] = self._current_status
            metadata["timestamp"] = datetime.now().isoformat()
            logger.debug("AVRCP メタデータ受信: %s", metadata.get("title", ""))
            self._callback(metadata)
        elif "Status" in changed:
            # Status のみの変更もカードを生成する（YouTube アプリ等、Track を送らないアプリ対応）
            status_key = f"status|{self._current_status}"
            now = time.time()
            if status_key == self._last_track_key and (now - self._last_track_time) < 2.0:
                logger.debug("重複ステータスをスキップ: %s", self._current_status)
                return
            self._last_track_key = status_key
            self._last_track_time = now

            logger.debug("AVRCP ステータス変更: %s", self._current_status)
            self._callback({
                "status": self._current_status,
                "timestamp": datetime.now().isoformat(),
                "title": "",
                "artist": "",
                "album": "",
                "genre": "",
                "track_number": None,
                "number_of_tracks": None,
                "duration_ms": None,
            })

    def _on_interfaces_added(self, path, interfaces):
        """新しい Bluetooth インターフェース追加の検出。"""
        interfaces = _dbus_to_python(interfaces)
        if "org.bluez.MediaPlayer1" in interfaces:
            logger.info("新しい MediaPlayer1 インターフェース検出: %s", path)

    # ── モックモード ──

    _MOCK_TRACKS = [
        # 通常の音楽（全フィールド充実）
        {
            "title": "Bohemian Rhapsody",
            "artist": "Queen",
            "album": "A Night at the Opera",
            "genre": "Rock",
            "track_number": 11,
            "number_of_tracks": 12,
            "duration_ms": 354000,
            "status": "playing",
        },
        {
            "title": "Blinding Lights",
            "artist": "The Weeknd",
            "album": "After Hours",
            "genre": "Synth-pop",
            "track_number": 9,
            "number_of_tracks": 14,
            "duration_ms": 200000,
            "status": "playing",
        },
        {
            "title": "Shape of You",
            "artist": "Ed Sheeran",
            "album": "÷ (Divide)",
            "genre": "Pop",
            "track_number": 4,
            "number_of_tracks": 16,
            "duration_ms": 233000,
            "status": "playing",
        },
        {
            "title": "Dynamite",
            "artist": "BTS",
            "album": "BE",
            "genre": "Pop",
            "track_number": 1,
            "number_of_tracks": 8,
            "duration_ms": 199000,
            "status": "playing",
        },
        # YouTube 風（Album 空、Duration 0）
        {
            "title": "【解説】最新テクノロジーまとめ 2026年版",
            "artist": "テック太郎",
            "album": "",
            "genre": "",
            "track_number": None,
            "number_of_tracks": None,
            "duration_ms": 0,
            "status": "playing",
        },
        {
            "title": "Lofi Hip Hop Radio - beats to relax/study to",
            "artist": "Lofi Girl",
            "album": "",
            "genre": "",
            "track_number": None,
            "number_of_tracks": None,
            "duration_ms": 0,
            "status": "playing",
        },
        # Podcast 風（Duration が長い、Genre が "Podcast"）
        {
            "title": "EP.142 AIの未来を語る",
            "artist": "テックポッドキャスト",
            "album": "Weekly Tech Talk",
            "genre": "Podcast",
            "track_number": 142,
            "number_of_tracks": None,
            "duration_ms": 3600000,
            "status": "playing",
        },
        {
            "title": "#58 スタートアップ創業者インタビュー",
            "artist": "ビジネスラジオ",
            "album": "起業家の本音",
            "genre": "Podcast",
            "track_number": 58,
            "number_of_tracks": None,
            "duration_ms": 2700000,
            "status": "playing",
        },
        # ラジオ風（情報が最小限）
        {
            "title": "TOKYO FM",
            "artist": "",
            "album": "",
            "genre": "",
            "track_number": None,
            "number_of_tracks": None,
            "duration_ms": None,
            "status": "playing",
        },
        {
            "title": "J-WAVE 81.3FM",
            "artist": "GROOVE LINE",
            "album": "",
            "genre": "",
            "track_number": None,
            "number_of_tracks": None,
            "duration_ms": None,
            "status": "playing",
        },
    ]

    def _mock_loop(self):
        """モックデータを定期的に生成するループ。"""
        logger.info("モックデータ生成ループを開始")

        while self._running:
            # 5〜15 秒のランダム間隔
            interval = random.uniform(5, 15)
            time.sleep(interval)

            if not self._running:
                break

            track = random.choice(self._MOCK_TRACKS).copy()
            # たまに paused を混ぜる
            if random.random() < 0.15:
                track["status"] = "paused"
            track["timestamp"] = datetime.now().isoformat()

            logger.debug("モックデータ生成: %s", track.get("title", ""))
            self._callback(track)
