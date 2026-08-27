import os
import sys
import time
import re
import io
import json
import math
import random
import socket
import threading
import subprocess
import shutil
import atexit
import urllib.request
import urllib.parse
import hashlib
import yt_dlp
import qrcode
import uuid
from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageFilter

CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

# パス解決ヘルパー
if getattr(sys, 'frozen', False):
    BASE_PATH = sys._MEIPASS
    APP_DIR = os.path.dirname(sys.executable)
else:
    BASE_PATH = os.path.dirname(os.path.abspath(__file__))
    APP_DIR = BASE_PATH

CONFIG_FILE = os.path.join(APP_DIR, "config.json")
HLS_DIR = os.path.join(APP_DIR, "hls_output")
IMAGE_CACHE_DIR = os.path.join(HLS_DIR, "images")
RADIO_CACHE_DIR = os.path.join(IMAGE_CACHE_DIR, "radio_cache")
STANDBY_IMAGE_PATH = os.path.join(HLS_DIR, "standby.png")
DEFAULT_STANDBY_IMAGE_PATH = os.path.join(BASE_PATH, "assets", "standby_default.jpg")
QR_OVERLAY_PATH = os.path.join(HLS_DIR, "qr_overlay.png")
CLOUDFLARED_EXE = os.path.join(BASE_PATH, "cloudflared.exe")
LOCAL_FFMPEG = os.path.join(APP_DIR, "ffmpeg.exe")
LOCAL_FFPROBE = os.path.join(APP_DIR, "ffprobe.exe")
VIDEO_STORAGE_DIR = os.path.join(HLS_DIR, "videos")

def cleanup_hls_dir_completely():
    """HLS出力ディレクトリ内の全一時ファイル・フォルダを完全消去する（atexit ハンドラ）。"""
    if not os.path.exists(HLS_DIR):
        return
    for attempt in range(5):
        try:
            remaining = False
            for item in os.listdir(HLS_DIR):
                item_path = os.path.join(HLS_DIR, item)
                try:
                    if os.path.isdir(item_path):
                        shutil.rmtree(item_path, ignore_errors=True)
                    else:
                        os.remove(item_path)
                except Exception:
                    remaining = True
            if not remaining and not os.listdir(HLS_DIR):
                break
            time.sleep(0.2)
        except Exception:
            time.sleep(0.2)

atexit.register(cleanup_hls_dir_completely)

def get_local_ip():
    """LAN内の自ホストIPアドレスを取得 (例: 192.168.1.100)"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return '127.0.0.1'

DEFAULT_CONFIG = {
    "host": "127.0.0.1",
    "port": 8000,
    "enable_tunnel": True,
    "hls_segment_time": 3,
    "hls_list_size": 15,
    "video_transition_wait_seconds": 1,
    "live_sync_duration_count": 4,
    "loop_queue": False,
    "shuffle": False,
    "allow_web_queue_add": True,
    "allow_web_queue_edit": True,
    "allow_web_playback_control": True,
    "image_display_duration": 15,
    "image_auto_advance": False,
    "overlay_qr_enabled": False,
    "overlay_qr_video": False,
    "overlay_qr_image": False,
    "overlay_qr_mode": "bottom-right",
    "overlay_clock_enabled": False,
    "overlay_clock_video": False,
    "overlay_clock_position": "top-right",
    "playback_mode": "video",
    "radio_mode": False,
    "radio_bg_source": "card",
    "standby_mode": "image",
    "standby_image_path": "",
    "web_password": "",
    "max_video_upload_mb": 200
}

def log_print(msg):
    try:
        print(msg, flush=True)
    except Exception:
        pass

def get_ffmpeg_cmd():
    if os.path.exists(LOCAL_FFMPEG):
        return LOCAL_FFMPEG
    return "ffmpeg"

def get_ffprobe_cmd():
    if os.path.exists(LOCAL_FFPROBE):
        return LOCAL_FFPROBE
    return "ffprobe"

def kill_proc(proc):
    if not proc:
        return
    try:
        proc.kill()
        try:
            proc.wait(timeout=2.0)
        except Exception:
            pass
    except Exception:
        pass

def get_drawtext_font_path(bold=True):
    """FFmpegのdrawtextフィルタ用にエスケープされたフォントパスを取得"""
    candidates = [
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/meiryob.ttc" if bold else "C:/Windows/Fonts/meiryo.ttc",
        "C:/Windows/Fonts/YuGothB.ttc" if bold else "C:/Windows/Fonts/YuGothM.ttc",
        "C:/Windows/Fonts/msgothic.ttc",
        "C:/Windows/Fonts/seguisb.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    font_path = None
    for p in candidates:
        if os.path.exists(p):
            font_path = p
            break
    if not font_path:
        font_path = "arialbd.ttf" if bold else "arial.ttf"

    # Windowsパスのバックスラッシュをスラッシュに変換し、コロンをエスケープ (e.g. C\:/Windows/Fonts/...)
    font_path = font_path.replace("\\", "/")
    font_path_escaped = font_path.replace(":", "\\:")
    return font_path_escaped

def get_live_clock_drawtext_filter(x="w-tw-45", y="26", font_size=28, bold=True):
    """リアルタイムLIVE時計オーバーレイ用 drawtext フィルタ文字列を生成"""
    font_path = get_drawtext_font_path(bold=bold)
    return (
        f"drawtext=fontfile='{font_path}':"
        f"text='● LIVE %{{localtime\\:%H\\:%M\\:%S}} JST':"
        f"fontsize={font_size}:fontcolor=white:"
        f"box=1:boxcolor=0x0F172A@0.82:boxborderw=8:"
        f"x={x}:y={y}"
    )

def get_clock_filter_for_config(config=None):
    """configの設定（overlay_clock_position）に基づいて drawtext フィルタ文字列を生成"""
    if config is None:
        config = {}
    clock_pos = config.get("overlay_clock_position", "top-right") if isinstance(config, dict) else "top-right"
    if clock_pos == "top-left":
        clock_x, clock_y = "45", "26"
    elif clock_pos == "bottom-right":
        clock_x, clock_y = "w-tw-45", "h-th-26"
    elif clock_pos == "bottom-left":
        clock_x, clock_y = "45", "h-th-26"
    else:  # "top-right" default
        clock_x, clock_y = "w-tw-45", "26"
    return get_live_clock_drawtext_filter(x=clock_x, y=clock_y, font_size=28)

def get_pil_font(size=24, bold=False):
    """PIL用の日本語対応フォントを安全に取得"""
    candidates = [
        "C:/Windows/Fonts/meiryob.ttc" if bold else "C:/Windows/Fonts/meiryo.ttc",
        "C:/Windows/Fonts/YuGothB.ttc" if bold else "C:/Windows/Fonts/YuGothM.ttc",
        "C:/Windows/Fonts/msgothic.ttc",
        "meiryob.ttc" if bold else "meiryo.ttc",
        "arialbd.ttf" if bold else "arial.ttf",
        "arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    ]
    for p in candidates:
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            continue
    return ImageFont.load_default()

MAX_PLAYLIST_ITEMS = 50
MAX_QUEUE_CAPACITY = 200
MAX_PHOTO_CAPACITY = 200

def is_safe_url(url):
    """URLが安全か（http/https、SSRF・ローカルアドレス拒否）を検証"""
    if not url or not isinstance(url, str):
        return False, "Empty or invalid URL"
    url = url.strip()
    if len(url) > 2048:
        return False, "URL too long (max 2048 chars)"

    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
    except Exception:
        return False, "Malformed URL"

    if parsed.scheme not in ("http", "https"):
        return False, f"Unsupported URL scheme '{parsed.scheme}'. Only http/https are allowed."

    host = (parsed.hostname or "").lower()
    if not host:
        return False, "Missing hostname in URL"

    # ローカル・プライベートIP、イントラネットアドレスのブロック (SSRF対策)
    blocked_hosts = ("localhost", "127.0.0.1", "0.0.0.0", "::1")
    if host in blocked_hosts or host.endswith(".local") or host.endswith(".lan") or host.endswith(".internal"):
        return False, "Access to local/private network addresses is forbidden"

    import ipaddress
    import socket

    def _is_forbidden_ip(ip_str):
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            return False
        # IPv4射影IPv6 (::ffff:127.0.0.1) は元のIPv4に戻して判定する
        mapped = getattr(ip, "ipv4_mapped", None)
        if mapped is not None:
            ip = mapped
        return (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified)

    # 表記そのものがIPアドレスの場合
    if _is_forbidden_ip(host):
        return False, "Access to private/loopback IP is forbidden"

    # ホスト名を実際に解決して判定する。
    # これにより 10進表記 (http://2130706433/) や、内部IPを指すドメイン名も弾ける。
    try:
        resolved = socket.getaddrinfo(host, None)
    except Exception:
        return False, "Hostname could not be resolved"

    for info in resolved:
        if _is_forbidden_ip(info[4][0]):
            return False, "Hostname resolves to a private/loopback address"

    return True, "OK"

def is_image_url_or_file(path_or_url):
    """パスまたはURLが画像形式かどうかを判定"""
    if not path_or_url or not isinstance(path_or_url, str):
        return False
    clean = path_or_url.split("?")[0].split("#")[0].lower()
    return clean.endswith((".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"))

def is_video_url_or_file(path_or_url):
    """パスまたはURLが動画形式かどうかを判定"""
    if not path_or_url or not isinstance(path_or_url, str):
        return False
    clean = path_or_url.split("?")[0].split("#")[0].lower()
    return clean.endswith((".mp4", ".mov", ".webm", ".mkv", ".avi", ".m4v", ".ts", ".flv"))

def get_video_file_duration(file_path):
    """ffprobe または ffmpeg を用いてローカル動画の再生時間（秒）を取得"""
    if not file_path or not os.path.exists(file_path):
        return 0.0
    try:
        cmd = [
            get_ffprobe_cmd(),
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            file_path
        ]
        res = subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, timeout=5,
            creationflags=CREATE_NO_WINDOW if os.name == 'nt' else 0
        )
        if res.returncode == 0 and res.stdout.strip():
            val = float(res.stdout.strip())
            if val > 0:
                return val
    except Exception:
        pass

    try:
        cmd = [get_ffmpeg_cmd(), "-i", file_path]
        res = subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, timeout=5,
            creationflags=CREATE_NO_WINDOW if os.name == 'nt' else 0
        )
        m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)", res.stderr)
        if m:
            hours, minutes, seconds = float(m.group(1)), float(m.group(2)), float(m.group(3))
            return hours * 3600 + minutes * 60 + seconds
    except Exception:
        pass
    return 0.0

def extract_pts_from_ts_chunk(chunk):
    """MPEG-TSチャンクから再生位置PTS（秒）を抽出する。

    映像PES・音声PESそれぞれの最新PTSを個別に拾い、**遅れている方（min）** を返す。
    以前は「チャンク内で最後に見つかったPTS」をそのまま返していたため、
    映像だけが音声より数十秒先行して多重化された場合（concat スライドショー背景で発生）、
    relay_stream_data のペーシングが先行した映像PTSを実際の配信位置と誤認し、
    先読みバッファ制御が効かずに実時間の数倍速で送出しきってしまっていた。
    配信位置として意味を持つのは遅れている側なので min を採用する。
    """
    length = len(chunk)
    if length < 188:
        return None
    latest_video_pts = None
    latest_audio_pts = None
    offset = 0
    while offset + 188 <= length:
        if chunk[offset] == 0x47:
            pkt = chunk[offset:offset+188]
            payload_unit_start = bool(pkt[1] & 0x40)
            adaptation_field_ctrl = (pkt[3] >> 4) & 0x03
            
            payload_offset = 4
            if adaptation_field_ctrl in (2, 3):
                adaptation_len = pkt[4]
                payload_offset += 1 + adaptation_len
                
            if payload_unit_start and payload_offset + 9 <= 188:
                if pkt[payload_offset] == 0x00 and pkt[payload_offset+1] == 0x00 and pkt[payload_offset+2] == 0x01:
                    stream_id = pkt[payload_offset+3]
                    is_video = 0xE0 <= stream_id <= 0xEF
                    is_audio = 0xC0 <= stream_id <= 0xDF
                    if is_video or is_audio:
                        flags2 = pkt[payload_offset+7]
                        pts_flag = (flags2 >> 7) & 0x01
                        if pts_flag and payload_offset + 14 <= 188:
                            b0 = pkt[payload_offset+9]
                            b1 = pkt[payload_offset+10]
                            b2 = pkt[payload_offset+11]
                            b3 = pkt[payload_offset+12]
                            b4 = pkt[payload_offset+13]
                            pts = (((b0 & 0x0E) << 29) | ((b1 & 0xFF) << 22) |
                                   ((b2 & 0xFE) << 14) | ((b3 & 0xFF) << 7) |
                                   ((b4 & 0xFE) >> 1))
                            pts_sec = pts / 90000.0
                            if is_video:
                                latest_video_pts = pts_sec
                            else:
                                latest_audio_pts = pts_sec
            offset += 188
        else:
            next_sync = chunk.find(b'\x47', offset + 1)
            if next_sync == -1:
                break
            offset = next_sync

    found = [p for p in (latest_video_pts, latest_audio_pts) if p is not None]
    if not found:
        return None
    return min(found)

class StreamerCore:
    def __init__(self, override_port=None, override_host=None, override_enable_tunnel=None):
        self.config = DEFAULT_CONFIG.copy()
        self.load_config()
        # コマンドライン引数による上書きは「その起動限りの指定」であり、config.json には焼き付けない。
        # 以前は self.config に直接載せていたため、UI から何か設定を変えて save_config() が走るたびに
        # --port / --host / --no-tunnel の値が config.json に永続化されていた。
        # これが「開発者がローカルテストした設定がそのまま配布物の既定値になる」原因だった。
        self._cli_override_baseline = {}
        for key, value in (("port", override_port), ("host", override_host)):
            if value is not None:
                self._cli_override_baseline[key] = self.config.get(key)
                self.config[key] = value
        if override_enable_tunnel is not None:
            self._cli_override_baseline["enable_tunnel"] = self.config.get("enable_tunnel")
            self.config["enable_tunnel"] = bool(override_enable_tunnel)

        self.enable_tunnel = bool(self.config.get("enable_tunnel", True))

        os.makedirs(HLS_DIR, exist_ok=True)
        self.clean_hls_dir(all_files=True, preserve_images=False)

        # プロセスと同期
        self.hls_proc = None
        self.send_proc = None
        self.tunnel_proc = None
        self.current_stdin = None

        self.play_queue = [] # list of dict: [{"title": "...", "url": "...", "duration": ..., "type": "video"}]
        self.photo_pool = [] # list of dict: [{"id": "...", "type": "image", "title": "...", "url": "...", "path": "...", "duration": ...}]
        self.history_stack = [] # 履歴管理用 (最大20件)
        self.queue_lock = threading.Lock()
        self.photo_lock = threading.Lock()
        self.process_lock = threading.Lock()
        self.slideshow_index = 0

        # 累積PTSとシームレス遷移管理
        self.accumulated_pts = 0.0
        self.last_stream_duration = 0.0
        self.prefetch_cache = {}
        self.prefetch_lock = threading.Lock()

        # 状態
        # status: "offline", "buffering", "streaming", "finishing", "error"
        self.status = "offline"
        self.status_detail = "Offline (Queue Empty)"
        self.current_video = None # {"title": "...", "url": "...", "duration": ..., "type": ...}
        self.tunnel_url = "" # "https://xxx.trycloudflare.com/stream.m3u8"
        self.tunnel_raw_url = "" # "https://xxx.trycloudflare.com"
        self.is_running = True
        self.image_paused = not bool(self.config.get("image_auto_advance", False)) # 写真スライドショー一時停止フラグ
        self.slideshow_cursor = 0 # ラジオ背景スライドショーの再生位置（曲をまたいで巡回させる）

        self.skip_event = threading.Event()
        self.video_done_event = threading.Event()
        self.reload_stream_event = threading.Event()
        self.current_video_start_time = None

    def clean_hls_dir(self, all_files=False, preserve_images=False):
        """HLS出力ディレクトリのクリーンアップ。

        all_files=True でサブディレクトリを含めて全削除する。
        preserve_images=True のときは images/（利用者がアップロードした写真と
        ラジオカードのキャッシュ）だけを残す。起動・終了のたびにここを消していたため、
        アップロード済みの写真が毎回失われ、ラジオ背景のスライドショーが
        「設定しても何も表示されない」状態になっていた。
        """
        if not os.path.exists(HLS_DIR):
            return
        preserved = {"images", "videos"} if preserve_images else set()
        for attempt in range(5):
            try:
                remaining = False
                for item in os.listdir(HLS_DIR):
                    if item in preserved:
                        continue
                    item_path = os.path.join(HLS_DIR, item)
                    if all_files:
                        try:
                            if os.path.isdir(item_path):
                                shutil.rmtree(item_path, ignore_errors=True)
                            else:
                                os.remove(item_path)
                        except Exception:
                            remaining = True
                    else:
                        if item.endswith(".ts") or item.endswith(".m3u8"):
                            try:
                                os.remove(item_path)
                            except Exception:
                                remaining = True
                if not remaining and (not all_files or not (set(os.listdir(HLS_DIR)) - preserved)):
                    break
                time.sleep(0.2)
            except Exception as e:
                log_print(f"[Core] Warning cleaning HLS dir: {e}")
                time.sleep(0.2)

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                    if isinstance(saved, dict):
                        self.config.update(saved)
                log_print(f"[Core] Loaded config from {CONFIG_FILE}")
            except Exception as e:
                log_print(f"[Core] Error reading config: {e}")

    def save_config(self, new_config=None):
        baseline = getattr(self, "_cli_override_baseline", {})
        if new_config:
            self.config.update(new_config)
            if "enable_tunnel" in new_config:
                self.enable_tunnel = bool(new_config["enable_tunnel"])
            # 利用者が明示的に変更した項目は、CLI上書きの対象から外して永続化する
            for key in [k for k in baseline if k in new_config]:
                del baseline[key]
        try:
            persisted = dict(self.config)
            # CLI 由来の一時的な上書きは、保存前に元の値へ戻す
            for key, original in baseline.items():
                if original is None:
                    persisted.pop(key, None)
                else:
                    persisted[key] = original
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(persisted, f, indent=2, ensure_ascii=False)
            log_print(f"[Core] Saved config to {CONFIG_FILE}")

            # 最新設定でQRオーバーレイ・待機画像を即座に再生成
            self.generate_qr_overlay_image()
            self.generate_standby_image()

            with self.queue_lock:
                is_queue_empty = (len(self.play_queue) == 0 and self.current_video is None)
                is_playing = (self.current_video is not None)

            # 待機中（キュー空）なら待機ストリームを即座にリロード
            if is_queue_empty and self.send_proc:
                log_print("[Core] Hot-reloading standby stream with updated settings...")
                with self.process_lock:
                    kill_proc(self.send_proc)
            elif is_playing:
                # 動画または写真の再生中なら、即座に現在のストリームをホットリロード
                log_print("[Core] Triggering hot-reload of active stream with updated settings...")
                self.reload_stream_event.set()

            return True
        except Exception as e:
            log_print(f"[Core] Failed to save config: {e}")
            return False

    def get_status_data(self):
        with self.queue_lock:
            queue_copy = [dict(item) for item in self.play_queue]
            has_prev = len(self.history_stack) >= 2

        port = self.config.get("port", 8000)
        if self.tunnel_raw_url:
            stream_url = f"{self.tunnel_raw_url}/stream.m3u8"
            public_url = self.tunnel_raw_url
        elif not self.enable_tunnel:
            stream_url = f"http://localhost:{port}/stream.m3u8"
            public_url = f"http://localhost:{port}"
        else:
            stream_url = ""
            public_url = ""

        is_image = bool(self.current_video and self.current_video.get("type") == "image")

        return {
            "status": self.status,
            "status_detail": self.status_detail,
            "tunnel_url": public_url,
            "stream_url": stream_url,
            "local_url": f"http://localhost:{port}",
            "enable_tunnel": self.enable_tunnel,
            "current_video": self.current_video,
            "queue": queue_copy,
            "loop_queue": bool(self.config.get("loop_queue", False)),
            "shuffle": bool(self.config.get("shuffle", False)),
            "is_image": is_image,
            "image_paused": self.image_paused,
            "image_display_duration": int(self.config.get("image_display_duration", 15)),
            "image_auto_advance": bool(self.config.get("image_auto_advance", False)),
            "overlay_qr_enabled": bool(self.config.get("overlay_qr_enabled", False) or self.config.get("overlay_qr_video", False) or self.config.get("overlay_qr_image", False)),
            "overlay_qr_video": bool(self.config.get("overlay_qr_video", False)),
            "overlay_qr_image": bool(self.config.get("overlay_qr_image", False)),
            "overlay_qr_mode": str(self.config.get("overlay_qr_mode", "bottom-right")),
            "overlay_clock_enabled": bool(self.config.get("overlay_clock_enabled", False) or self.config.get("overlay_clock_video", False)),
            "overlay_clock_video": bool(self.config.get("overlay_clock_video", False)),
            "overlay_clock_position": str(self.config.get("overlay_clock_position", "top-right")),
            "playback_mode": self.get_playback_mode(),
            "photos": self.get_photos(),
            "photo_count": len(self.get_photos()),
            "radio_mode": (self.get_playback_mode() == "radio"),
            "radio_bg_source": str(self.config.get("radio_bg_source", "standby")),
            "standby_mode": str(self.config.get("standby_mode", "image")),
            "standby_image_path": str(self.config.get("standby_image_path", "")),
            "has_prev": has_prev,
            "has_web_password": bool(str(self.config.get("web_password", "")).strip()),
            "permissions": {
                "allow_web_queue_add": bool(self.config.get("allow_web_queue_add", True)),
                "allow_web_queue_edit": bool(self.config.get("allow_web_queue_edit", True)),
                "allow_web_playback_control": bool(self.config.get("allow_web_playback_control", True))
            }
        }

    def get_playback_mode(self):
        """現在の再生モード ('video' | 'radio' | 'slideshow') を取得"""
        mode = self.config.get("playback_mode")
        if mode in ("video", "radio", "slideshow"):
            return mode
        if self.config.get("radio_mode", False):
            return "radio"
        return "video"

    def set_playback_mode(self, mode: str):
        """再生モードを設定 ('video' | 'radio' | 'slideshow')"""
        if mode not in ("video", "radio", "slideshow"):
            log_print(f"[Core] Invalid playback mode: {mode}")
            return self.get_playback_mode()

        self.config["playback_mode"] = mode
        self.config["radio_mode"] = (mode == "radio")
        self.save_config()
        self.reload_stream_event.set()
        log_print(f"[Core] Playback mode set to: {mode}")
        return mode

    def set_standby_config(self, mode: str = None, image_path: str = None):
        if mode in ("image", "qr"):
            self.config["standby_mode"] = mode
        if image_path is not None:
            self.config["standby_image_path"] = image_path
        self.save_config()
        self.generate_standby_image()
        log_print(f"[Core] Standby config updated: mode={self.config.get('standby_mode')}, image_path={self.config.get('standby_image_path')}")
        return self.config.get("standby_mode")

    def set_overlay_clock(self, enabled: bool, video: bool = None, position: str = None):
        self.config["overlay_clock_enabled"] = bool(enabled)
        if video is not None:
            self.config["overlay_clock_video"] = bool(video)
        if position is not None and position in ("top-right", "top-left", "bottom-right", "bottom-left"):
            self.config["overlay_clock_position"] = position
        self.save_config()
        log_print(f"[Core] Clock overlay config updated: enabled={self.config['overlay_clock_enabled']}, video={self.config.get('overlay_clock_video', False)}, pos={self.config.get('overlay_clock_position', 'top-right')}")
        return self.config["overlay_clock_enabled"]

    def set_radio_mode(self, enabled: bool):
        mode = "radio" if enabled else "video"
        return (self.set_playback_mode(mode) == "radio")

    def set_radio_bg_source(self, source: str):
        if source in ("card", "standby", "slideshow"):
            self.config["radio_bg_source"] = source
            self.save_config()
            log_print(f"[Core] Radio background source set to: {source}")
        return self.config.get("radio_bg_source", "card")

    def set_loop(self, enabled: bool):
        self.config["loop_queue"] = bool(enabled)
        self.save_config()
        log_print(f"[Core] Loop queue set to: {self.config['loop_queue']}")
        return self.config["loop_queue"]

    def set_shuffle(self, enabled: bool):
        self.config["shuffle"] = bool(enabled)
        self.save_config()
        log_print(f"[Core] Shuffle set to: {self.config['shuffle']}")
        return self.config["shuffle"]

    def shuffle_queue(self):
        with self.queue_lock:
            random.shuffle(self.play_queue)
        log_print("[Core] Queue shuffled.")
        return True

    def toggle_image_pause(self):
        curr_advance = bool(self.config.get("image_auto_advance", False)) and not self.image_paused
        new_advance = not curr_advance
        self.set_image_auto_advance(new_advance)
        return self.image_paused

    def set_image_pause(self, paused: bool):
        self.image_paused = bool(paused)
        self.config["image_auto_advance"] = not self.image_paused
        self.save_config()
        log_print(f"[Core] Photo pause set to: {self.image_paused} (auto_advance: {self.config['image_auto_advance']})")
        return self.image_paused

    def set_image_duration(self, seconds: int):
        try:
            sec = max(3, min(600, int(seconds)))
            self.config["image_display_duration"] = sec
            self.save_config()
            log_print(f"[Core] Photo display duration set to: {sec}s")
            return sec
        except Exception:
            return self.config.get("image_display_duration", 15)

    def set_image_auto_advance(self, enabled: bool):
        self.config["image_auto_advance"] = bool(enabled)
        self.image_paused = not bool(enabled)
        self.save_config()
        log_print(f"[Core] Photo auto advance set to: {self.config['image_auto_advance']}")
        return self.config["image_auto_advance"]

    def play_prev(self):
        """直前に再生したアイテムに戻る"""
        with self.queue_lock:
            if len(self.history_stack) >= 2:
                # 現在再生中の履歴をポップ
                self.history_stack.pop()
                prev_item = self.history_stack.pop()
                # 現在のアイテムをキュー先頭に復元
                if self.current_video:
                    self.play_queue.insert(0, self.current_video)
                # prev_item をキューの最前面に挿入
                self.play_queue.insert(0, prev_item)
                log_print(f"[Core] Navigating to prev item: {prev_item.get('title')}")
                self.skip_video()
                return True
        log_print("[Core] No previous item in history.")
        return False

    def ensure_hls_receiver(self):
        """HLS受信FFmpegが動いていれば維持し、未起動/停止時のみ起動する（ストリーム連続性を保持）"""
        with self.process_lock:
            if self.hls_proc and self.hls_proc.poll() is None and self.current_stdin:
                return True

            if self.hls_proc:
                kill_proc(self.hls_proc)
                self.hls_proc = None
                self.current_stdin = None
                time.sleep(0.2)

        seg_time = str(self.config.get("hls_segment_time", 3))
        list_size = str(self.config.get("hls_list_size", 15))

        cmd = [
            get_ffmpeg_cmd(), "-y",
            "-fflags", "+nobuffer+flush_packets+genpts+igndts",
            "-i", "pipe:0",
            "-c:v", "copy",
            "-c:a", "copy",
            "-flush_packets", "1",
            "-f", "hls",
            "-hls_time", seg_time,
            "-hls_list_size", list_size,
            "-hls_flags", "delete_segments+split_by_time+append_list",
            "-hls_segment_filename", os.path.join(HLS_DIR, "seg_%05d.ts"),
            os.path.join(HLS_DIR, "stream.m3u8"),
        ]

        try:
            proc = subprocess.Popen(
                cmd, stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=CREATE_NO_WINDOW
            )
            with self.process_lock:
                self.hls_proc = proc
                self.current_stdin = proc.stdin
            log_print(f"[Receiver] Persistent HLS FFmpeg started (segment_time: {seg_time}s, list_size: {list_size}).")
            return True
        except FileNotFoundError:
            log_print("[Receiver] Error: ffmpeg was not found in system path.")
            return False
        except Exception as e:
            log_print(f"[Receiver] Error starting HLS FFmpeg: {e}")
            return False

    def relay_stream_data(self, proc_to_read, stdin_to_write, stop_event, is_paced=True):
        """
        送信側FFmpegから受信側HLS FFmpegへのストリーム中継。
        is_paced=True の場合、初期バースト（約15秒分）を高速生成後、
        実時間 + 先読みバッファ（15秒）を維持するようにデータ流量を制御する。
        """
        BUFFER_AHEAD_SECONDS = 15.0  # 先行バッファ秒数
        base_pts = None
        current_stream_pos = 0.0
        max_relative_pts = 0.0
        start_wall_time = time.time()

        try:
            while not stop_event.is_set() and self.is_running:
                if hasattr(proc_to_read.stdout, "read1"):
                    data = proc_to_read.stdout.read1(65536)
                else:
                    data = proc_to_read.stdout.read(65536)

                if not data:
                    break

                pts = extract_pts_from_ts_chunk(data)
                if pts is not None:
                    if base_pts is None:
                        base_pts = pts
                    stream_pos = pts - base_pts
                    if stream_pos >= 0:
                        current_stream_pos = stream_pos
                        if current_stream_pos > max_relative_pts:
                            max_relative_pts = current_stream_pos

                # PTSの抽出と再生進捗の更新（ペーシング有効時）
                if is_paced:
                    # 先行秒数が目標バッファ（15秒）に収まるまで「実時間が追いつくのを待ち切る」。
                    # 以前は1チャンクにつき最大0.2秒しか眠らなかったため、
                    # 送信側FFmpegの出力レートが高いと待機が追いつかず先行秒数が青天井に増加し、
                    # 曲の残り全部を数十秒で送出しきってプレイリスト更新が止まっていた
                    # （＝視聴側ではセグメントが尽きて配信停止に見える）。
                    while not stop_event.is_set() and self.is_running:
                        wall_elapsed = time.time() - start_wall_time
                        ahead = current_stream_pos - wall_elapsed
                        if ahead <= BUFFER_AHEAD_SECONDS:
                            break
                        time.sleep(min(0.2, max(0.02, ahead - BUFFER_AHEAD_SECONDS)))

                try:
                    stdin_to_write.write(data)
                    stdin_to_write.flush()
                except Exception:
                    break
        except Exception:
            pass
        finally:
            dur = max_relative_pts if max_relative_pts > 0 else (time.time() - start_wall_time)
            self.last_stream_duration = max(1.0, dur)
            if not stop_event.is_set():
                self.video_done_event.set()

    def watch_send_proc(self, proc, stop_event):
        try:
            proc.wait()
        except Exception:
            pass
        if not stop_event.is_set():
            log_print("[Monitor] Video finished naturally.")
            self.video_done_event.set()

    def get_base_ydl_opts(self):
        """yt-dlp の基本共通オプションを生成（JSチャレンジ問題回避・安定したクライアントフォールバック）"""
        opts = {
            "quiet": True,
            "no_warnings": True,
            "nocheckcertificate": True,
            "extractor_args": {
                "youtube": {
                    "player_client": ["android", "ios", "tv", "web"]
                }
            }
        }
        cookie_path = os.path.abspath("cookies.txt")
        if os.path.exists(cookie_path):
            opts["cookiefile"] = cookie_path
        return opts

    def expand_playlist(self, url):
        """URLから動画情報リスト [{"url": ..., "title": ..., "duration": ...}] を展開"""
        is_safe, reason = is_safe_url(url)
        if not is_safe:
            log_print(f"[Core] Rejected unsafe URL: {reason}")
            return []

        ydl_opts = self.get_base_ydl_opts()
        ydl_opts.update({
            "extract_flat": True,
            "skip_download": True,
            "playlistend": MAX_PLAYLIST_ITEMS
        })
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if "entries" in info:
                    entries = list(info["entries"])[:MAX_PLAYLIST_ITEMS]
                    result = []
                    for e in entries:
                        if not e:
                            continue
                        e_url = e.get("url") or (f"https://www.youtube.com/watch?v={e['id']}" if e.get("id") else "")
                        if not e_url.startswith("http"):
                            e_url = f"https://www.youtube.com/watch?v={e.get('id', '')}"
                        result.append({
                            "url": e_url,
                            "title": e.get("title", "Unknown"),
                            "duration": e.get("duration", 0)
                        })
                    return result
                else:
                    return [{
                        "url": url,
                        "title": info.get("title", "Unknown"),
                        "duration": info.get("duration", 0)
                    }]
        except Exception as e:
            log_print(f"[Core] Failed to analyze URL: {e}")
            return []

    def get_stream_urls(self, youtube_url):
        ydl_opts = self.get_base_ydl_opts()
        ydl_opts.update({
            "format": "bestvideo[vcodec^=avc1]+bestaudio[acodec^=mp4a]/best[vcodec^=avc1]/bestvideo+bestaudio/best",
        })
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(youtube_url, download=False)
            video_url = audio_url = None
            headers = info.get("http_headers", {})
            if "requested_formats" in info:
                for fmt in info["requested_formats"]:
                    if fmt.get("vcodec") != "none" and fmt.get("acodec") == "none":
                        video_url = fmt.get("url")
                        if fmt.get("http_headers"):
                            headers.update(fmt["http_headers"])
                    elif fmt.get("acodec") != "none" and fmt.get("vcodec") == "none":
                        audio_url = fmt.get("url")
                        if fmt.get("http_headers"):
                            headers.update(fmt["http_headers"])
            if not video_url or not audio_url:
                video_url = info.get("url")
                audio_url = None
                if info.get("http_headers"):
                    headers.update(info["http_headers"])
            
            return video_url, audio_url, info.get("title", "Unknown"), info.get("duration", 0), headers

    def get_audio_only_stream_urls(self, youtube_url):
        ydl_opts = self.get_base_ydl_opts()
        ydl_opts.update({
            "format": "bestaudio[acodec^=mp4a]/bestaudio/best",
        })
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(youtube_url, download=False)
            audio_url = info.get("url")
            headers = info.get("http_headers", {})
            if "requested_formats" in info:
                for fmt in info["requested_formats"]:
                    if fmt.get("acodec") != "none":
                        audio_url = fmt.get("url")
                        if fmt.get("http_headers"):
                            headers.update(fmt["http_headers"])
            title = info.get("title", "Unknown")
            duration = info.get("duration", 0)
            meta = {
                "id": info.get("id", ""),
                "title": title,
                "duration": duration,
                "thumbnail": info.get("thumbnail", ""),
                "artist": info.get("artist") or info.get("creator") or info.get("uploader") or info.get("channel") or "",
                "channel": info.get("channel") or info.get("uploader") or ""
            }
            return audio_url, title, duration, headers, meta

    def prefetch_item(self, item):
        """次の動画/音楽のストリームURLおよびサムネイル画像をバックグラウンドで先読み"""
        if not item or item.get("type") == "image":
            return
        url = item.get("url")
        if not url or not url.startswith("http"):
            return

        with self.prefetch_lock:
            cached = self.prefetch_cache.get(url)
            if cached and (time.time() - cached.get("timestamp", 0) < 600):
                return

        is_radio = bool(self.config.get("radio_mode", False))
        log_print(f"[Prefetch] Starting prefetch for next item: {item.get('title')} (radio={is_radio})")

        try:
            if is_radio:
                res = self.get_audio_only_stream_urls(url)
                if res and res[0]:
                    audio_url, title, duration, headers, meta = res if len(res) >= 5 else (*res[:4], {})
                    bg_source = self.config.get("radio_bg_source", "card")
                    if bg_source == "card":
                        self.generate_radio_card_image(item, metadata=meta)
                    with self.prefetch_lock:
                        self.prefetch_cache[url] = {
                            "is_radio": True,
                            "audio_url": audio_url,
                            "title": title,
                            "duration": duration,
                            "headers": headers,
                            "meta": meta,
                            "timestamp": time.time()
                        }
                    log_print(f"[Prefetch] Completed prefetch for: {title}")
            else:
                res = self.get_stream_urls(url)
                if res and (res[0] or res[1]):
                    video_url, audio_url, title, duration, headers = res
                    with self.prefetch_lock:
                        self.prefetch_cache[url] = {
                            "is_radio": False,
                            "video_url": video_url,
                            "audio_url": audio_url,
                            "title": title,
                            "duration": duration,
                            "headers": headers,
                            "timestamp": time.time()
                        }
                    log_print(f"[Prefetch] Completed prefetch for: {title}")
        except Exception as e:
            log_print(f"[Prefetch] Failed to prefetch item: {e}")

    def generate_radio_card_image(self, video_info, metadata=None):
        """YouTubeサムネイルとタイトル・アーティスト情報を合成した 1920x1080 カード画像を生成"""
        os.makedirs(RADIO_CACHE_DIR, exist_ok=True)
        url = (video_info or {}).get("url", "")
        title = (metadata or {}).get("title") or (video_info or {}).get("title", "Unknown")
        artist = (metadata or {}).get("artist") or (metadata or {}).get("uploader") or (metadata or {}).get("channel") or ""
        video_id = (metadata or {}).get("id")

        if not video_id and "v=" in url:
            try:
                video_id = url.split("v=")[1].split("&")[0]
            except Exception:
                pass
        if not video_id and "youtu.be/" in url:
            try:
                video_id = url.split("youtu.be/")[1].split("?")[0]
            except Exception:
                pass
        if not video_id:
            import hashlib
            video_id = hashlib.md5(url.encode('utf-8', errors='ignore')).hexdigest()[:12]

        cache_path = os.path.join(RADIO_CACHE_DIR, f"radio_card_{video_id}.png")
        if os.path.exists(cache_path):
            return cache_path

        # サムネイル画像の取得
        thumb_img = None
        thumb_url = (metadata or {}).get("thumbnail")
        thumb_candidates = []
        if thumb_url:
            thumb_candidates.append(thumb_url)
        if video_id and len(video_id) == 11:
            thumb_candidates.append(f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg")
            thumb_candidates.append(f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg")

        for turl in thumb_candidates:
            try:
                req = urllib.request.Request(turl, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=5) as resp:
                    data = resp.read()
                    img = Image.open(io.BytesIO(data))
                    # YouTubeのmaxresdefaultが404でなく120x90の灰画像の場合のチェック
                    if img.size[0] > 150:
                        thumb_img = img.convert("RGB")
                        break
            except Exception:
                continue

        width, height = 1920, 1080
        card_img = Image.new("RGB", (width, height), color="#0F172A")

        # 1. 背景レイヤー (サムネイル拡大ぼかし + 落ち着いたダークオーバーレイ)
        if thumb_img:
            tw, th = thumb_img.size
            scale = max(width / tw, height / th)
            bw = int(tw * scale)
            bh = int(th * scale)
            bg_resized = thumb_img.resize((bw, bh), Image.Resampling.BILINEAR)
            bx = (bw - width) // 2
            by = (bh - height) // 2
            bg_cropped = bg_resized.crop((bx, by, bx + width, by + height))
            
            # ガウスぼかし
            bg_blurred = bg_cropped.filter(ImageFilter.GaussianBlur(radius=40))
            
            # ダークスレートの半透明オーバーレイ
            overlay = Image.new("RGBA", (width, height), (15, 23, 42, 215))
            bg_blurred = bg_blurred.convert("RGBA")
            bg_final = Image.alpha_composite(bg_blurred, overlay).convert("RGB")
            card_img.paste(bg_final, (0, 0))
        else:
            draw_bg = ImageDraw.Draw(card_img)
            draw_bg.rectangle([(0, 0), (width, height)], fill="#0F172A")

        draw = ImageDraw.Draw(card_img)

        # 2. 左側: アルバムアート (サムネイル) 描画
        art_w, art_h = 760, 428 # 16:9
        art_x = 120
        art_y = (height - art_h) // 2

        if thumb_img:
            tw, th = thumb_img.size
            scale = max(art_w / tw, art_h / th)
            aw = int(tw * scale)
            ah = int(th * scale)
            art_resized = thumb_img.resize((aw, ah), Image.Resampling.LANCZOS)
            ax = (aw - art_w) // 2
            ay = (ah - art_h) // 2
            art_cropped = art_resized.crop((ax, ay, ax + art_w, ay + art_h)).convert("RGBA")

            # 角丸マスク
            mask = Image.new("L", (art_w, art_h), 0)
            mask_draw = ImageDraw.Draw(mask)
            mask_draw.rounded_rectangle([(0, 0), (art_w, art_h)], radius=18, fill=255)

            card_art = Image.new("RGBA", (art_w, art_h), (0, 0, 0, 0))
            card_art.paste(art_cropped, (0, 0), mask)
            
            art_border_draw = ImageDraw.Draw(card_art)
            art_border_draw.rounded_rectangle([(0, 0), (art_w - 1, art_h - 1)], radius=18, outline=(255, 255, 255, 60), width=2)

            card_img.paste(card_art, (art_x, art_y), card_art)
        else:
            draw.rounded_rectangle(
                [(art_x, art_y), (art_x + art_w, art_y + art_h)],
                radius=18,
                fill="#1E293B",
                outline="#334155",
                width=2
            )
            try:
                font_icon = ImageFont.truetype("arial.ttf", 60)
            except Exception:
                font_icon = ImageFont.load_default()
            draw.text((art_x + art_w // 2, art_y + art_h // 2), "🎵", fill="#94A3B8", anchor="mm", font=font_icon)

        # 3. 中央〜右側: 楽曲情報 (タイトル・アーティスト) 描画
        info_x = art_x + art_w + 90
        max_text_w = width - info_x - 100

        font_title = get_pil_font(50, bold=True)
        font_artist = get_pil_font(32, bold=False)
        font_resync = get_pil_font(22, bold=False)

        clean_title = title.replace("📻 ", "").strip()
        lines = []
        curr_line = ""
        for char in clean_title:
            test_line = curr_line + char
            try:
                bbox = font_title.getbbox(test_line)
                w = bbox[2] - bbox[0]
            except Exception:
                w = len(test_line) * 28
            if w > max_text_w:
                if curr_line:
                    lines.append(curr_line)
                    curr_line = char
                else:
                    lines.append(test_line)
                    curr_line = ""
                if len(lines) >= 3:
                    break
            else:
                curr_line = test_line
        if curr_line and len(lines) < 3:
            lines.append(curr_line)
        if not lines:
            lines = [clean_title]

        line_h = 64
        title_total_h = len(lines) * line_h
        artist_h = 44 if artist else 0
        content_total_h = title_total_h + (35 if artist else 0) + artist_h

        start_y = (height - content_total_h) // 2

        for i, l in enumerate(lines):
            if i == 2 and len(clean_title) > len("".join(lines)):
                l = l[:-2] + "..." if len(l) > 2 else l + "..."
            draw.text((info_x, start_y + i * line_h), l, fill="#FFFFFF", anchor="la", font=font_title)

        if artist:
            artist_y = start_y + title_total_h + 30
            draw.text((info_x, artist_y), artist, fill="#38BDF8", anchor="la", font=font_artist)

        # 4. フッター: リシンク案内バー
        footer_h = 60
        draw.rectangle([(0, height - footer_h), (width, height)], fill="#0B1120")
        draw.text(
            (width // 2, height - footer_h // 2),
            "🔄 映像が止まった・遅れた時は [Resync] を押してください / If lagging or frozen, please press Resync.",
            fill="#94A3B8",
            anchor="mm",
            font=font_resync
        )

        try:
            card_img.save(cache_path, "PNG")
            return cache_path
        except Exception as e:
            log_print(f"[Radio] Failed to save radio card: {e}")
            return None

    def get_slideshow_images(self):
        """スライドショーで利用可能な画像パス一覧を取得（写真プール photo_pool から取得）"""
        with self.photo_lock:
            images = [
                os.path.abspath(p["path"])
                for p in self.photo_pool
                if p.get("path") and os.path.exists(p["path"])
            ]

        # シャッフル設定が有効ならシャッフル
        if self.config.get("shuffle", False) and len(images) > 1:
            images_copy = list(images)
            random.shuffle(images_copy)
            return images_copy

        return images

    def get_radio_background_path(self, video_info=None, metadata=None):
        """BGM/ラジオモード用の背景画像パスを取得（カード画面、待機画面、または写真）"""
        source = self.config.get("radio_bg_source", "card")
        if source == "card" and video_info:
            card_path = self.generate_radio_card_image(video_info, metadata)
            if card_path and os.path.exists(card_path):
                return card_path

        if source == "slideshow":
            images = self.get_slideshow_images()
            if images:
                return self.get_image_for_playback(images[0])

        # デフォルト・フォールバックは待機画面 (QR & URLカード付き)
        self.generate_standby_image()
        if os.path.exists(STANDBY_IMAGE_PATH):
            return STANDBY_IMAGE_PATH
        return None

    def play_radio(self, video_info, seek_seconds=0):
        """BGM/ラジオモード: YouTube音声ストリーム / ローカル動画音声 + 静止画/写真を合成し、極小帯域でHLS配信"""
        url = video_info.get("url", "")
        is_local = bool(video_info.get("is_local") or video_info.get("type") == "local_video" or (video_info.get("path") and os.path.exists(video_info["path"])))
        try:
            if is_local:
                audio_url = os.path.abspath(video_info.get("path") or url)
                title = video_info.get("title") or os.path.splitext(os.path.basename(audio_url))[0]
                duration = video_info.get("duration", 0)
                if not duration:
                    duration = get_video_file_duration(audio_url)
                headers = None
                metadata = {
                    "title": title,
                    "artist": "Local Video",
                    "duration": duration,
                    "id": video_info.get("id", "")
                }
                log_print(f"[Radio] Using local video audio: {title}")
            else:
                cached = None
                with self.prefetch_lock:
                    if url in self.prefetch_cache and self.prefetch_cache[url].get("is_radio"):
                        c = self.prefetch_cache.pop(url)
                        if time.time() - c.get("timestamp", 0) < 600:
                            cached = c

                if cached:
                    audio_url = cached["audio_url"]
                    title = cached["title"]
                    duration = cached["duration"]
                    headers = cached["headers"]
                    metadata = cached.get("meta") or {"title": title, "duration": duration}
                    log_print(f"[Radio] Using pre-fetched audio URL for: {title}")
                else:
                    res = self.get_audio_only_stream_urls(url)
                    if len(res) >= 5:
                        audio_url, title, duration, headers, metadata = res[:5]
                    else:
                        audio_url, title, duration, headers = res[:4]
                        metadata = {"title": title, "duration": duration}

            if not audio_url:
                raise ValueError("No audio stream URL returned")
            self.current_video = {
                "title": f"📻 {title}",
                "url": url,
                "duration": duration,
                "is_radio": True
            }
            self.current_video_start_time = time.time() - max(0, seek_seconds)
            log_print(f"[Radio] Now Playing (BGM Audio): {title} (seek: {int(seek_seconds)}s, pts_offset: {self.accumulated_pts:.2f}s)")
        except Exception as e:
            log_print(f"[Radio] Failed to get audio stream URL: {e}")
            self.current_video = {"title": f"Failed: {video_info.get('title', 'Unknown')}", "url": url, "duration": 0, "is_radio": True}
            self.status = "error"
            self.status_detail = "Failed to load audio stream"
            return None

        if not self.ensure_hls_receiver():
            self.current_video = {"title": "FFmpeg Error (Check PATH)", "url": url, "duration": 0, "is_radio": True}
            self.status = "error"
            self.status_detail = "FFmpeg Error"
            return None

        source = self.config.get("radio_bg_source", "card")
        auto_advance = bool(self.config.get("image_auto_advance", False)) and not self.image_paused

        slideshow_manifest_path = None
        if source == "slideshow" and auto_advance:
            images = self.get_slideshow_images()
            if images:
                duration_val = float(self.config.get("image_display_duration", 15))

                # スライドショーは曲をまたいで続きから再生する。
                # concat + -stream_loop -1 は常にマニフェストの先頭から再生されるため、
                # 「写真枚数 x 表示秒数」が曲の長さを超えると後半の写真が一度も表示されないまま
                # 次の曲でまた1枚目に戻ってしまい、特定の写真が永久にスキップされていた。
                # 曲ごとに開始位置をずらし、消化した枚数だけカーソルを進めることで全写真を巡回させる。
                start = self.slideshow_cursor % len(images)
                images = images[start:] + images[:start]
                try:
                    track_seconds = float(duration or 0)
                except (TypeError, ValueError):
                    track_seconds = 0.0
                if track_seconds > 0 and duration_val > 0:
                    consumed = max(1, int(math.ceil(track_seconds / duration_val)))
                else:
                    consumed = 1
                self.slideshow_cursor = (start + consumed) % len(images)

                manifest_lines = ["ffconcat version 1.0\n"]
                for idx, img in enumerate(images):
                    pb_path = self.get_image_for_playback(img, unique_id=idx)
                    pb_path_clean = os.path.abspath(pb_path).replace("\\", "/")
                    manifest_lines.append(f"file '{pb_path_clean}'\n")
                    manifest_lines.append(f"duration {duration_val}\n")
                # concat demuxer の最終要素の持続時間を有効にするため末尾に複製
                last_pb = self.get_image_for_playback(images[-1], unique_id=len(images))
                last_pb_clean = os.path.abspath(last_pb).replace("\\", "/")
                manifest_lines.append(f"file '{last_pb_clean}'\n")

                os.makedirs(IMAGE_CACHE_DIR, exist_ok=True)
                slideshow_manifest_path = os.path.join(IMAGE_CACHE_DIR, "slideshow_manifest.txt")
                with open(slideshow_manifest_path, "w", encoding="utf-8") as f:
                    f.writelines(manifest_lines)
                log_print(f"[Radio] Prepared slideshow manifest with {len(images)} photos (duration: {duration_val}s/photo, start #{start + 1}, next #{self.slideshow_cursor + 1}).")

        if slideshow_manifest_path and os.path.exists(slideshow_manifest_path):
            video_input_opts = [
                "-stream_loop", "-1",
                "-f", "concat",
                "-safe", "0",
                "-i", os.path.abspath(slideshow_manifest_path)
            ]
        else:
            bg_path = self.get_radio_background_path(video_info, metadata)
            if not bg_path or not os.path.exists(bg_path):
                self.generate_standby_image()
                bg_path = STANDBY_IMAGE_PATH
            video_input_opts = [
                "-loop", "1",
                "-i", os.path.abspath(bg_path)
            ]

        headers_str = ""
        if headers:
            headers_str = "".join(f"{k}: {v}\r\n" for k, v in headers.items())

        input_opts = []
        if not is_local:
            input_opts.extend([
                "-reconnect", "1",
                "-reconnect_streamed", "1",
                "-reconnect_delay_max", "2",
                "-reconnect_on_network_error", "1",
                "-reconnect_on_http_error", "4xx,5xx",
                "-rw_timeout", "10000000",
            ])
            if headers_str:
                input_opts.extend(["-headers", headers_str])
        if seek_seconds > 0:
            input_opts.extend(["-ss", str(int(seek_seconds))])

        clock_video = bool(self.config.get("overlay_clock_enabled", False) or self.config.get("overlay_clock_video", False))
        has_clock = bool(clock_video)
        clock_filter = get_clock_filter_for_config(self.config) if has_clock else None

        # QRオーバーレイ判定（スライドショーは get_image_for_playback で合成済みのため除外）
        is_slideshow = bool(slideshow_manifest_path and os.path.exists(slideshow_manifest_path))
        overlay_radio = bool(self.config.get("overlay_qr_enabled", False)) and not is_slideshow
        qr_overlay_file = self.generate_qr_overlay_image() if overlay_radio else None
        has_qr = bool(overlay_radio and qr_overlay_file and os.path.exists(qr_overlay_file))

        cmd = [get_ffmpeg_cmd()]
        if self.accumulated_pts > 0:
            cmd.extend(["-output_ts_offset", f"{self.accumulated_pts:.3f}"])
        cmd.extend(video_input_opts)           # [0] = 静止画 or concat
        cmd.extend(input_opts)
        cmd.extend(["-i", audio_url])           # [1] = YouTube音声

        if has_qr:
            cmd.extend(["-loop", "1", "-i", os.path.abspath(qr_overlay_file)])  # [2] = QRオーバーレイ
            qr_mode = self.config.get("overlay_qr_mode", "bottom-right")
            overlay_filter = self._build_video_filter_complex(
                has_qr=True, has_clock=has_clock, qr_idx=2, qr_mode=qr_mode, clock_filter=clock_filter
            )
            cmd.extend([
                "-filter_complex", overlay_filter,
                "-map", "[vout]",
                "-map", "1:a:0",
            ])
        elif has_clock and clock_filter:
            cmd.extend([
                "-map", "0:v:0",
                "-map", "1:a:0",
                "-vf", clock_filter,
            ])
        else:
            cmd.extend([
                "-map", "0:v:0",
                "-map", "1:a:0",
            ])
        cmd.extend([
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-tune", "zerolatency",
            "-profile:v", "baseline",
            "-level", "3.1",
            "-bf", "0",
            "-g", "15",
            "-keyint_min", "15",
            "-sc_threshold", "0",
            "-pix_fmt", "yuv420p",
            "-r", "2",
            "-b:v", "200k",
            "-maxrate", "250k",
            "-bufsize", "200k",
            "-c:a", "aac",
            "-b:a", "128k",
            "-ar", "44100",
            "-af", "aresample=async=1",
            "-shortest",
            "-fflags", "+nobuffer+flush_packets",
            "-flush_packets", "1",
            "-muxdelay", "0",
            "-muxpreload", "0",
            # 映像と音声を必ず時刻順に多重化する（先行した側を待ち合わせる）。
            # スライドショー背景は concat + -stream_loop -1 のため、マニフェストが
            # 一周するたびに映像PTSだけが音声より十数秒〜25秒先へ飛び、
            # 既定の max_interleave_delta(10秒) を超えて「過去に戻るDTS」を
            # 受信側FFmpegへ流し込んでいた。受信側HLS multiplexerはそこで
            # セグメント出力を停止し、配信が固まっていた。
            "-max_interleave_delta", "0",
            "-f", "mpegts", "pipe:1"
        ])

        try:
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, bufsize=0,
                creationflags=CREATE_NO_WINDOW
            )
        except Exception as e:
            log_print(f"[Radio] Error starting Radio sender: {e}")
            self.status = "error"
            self.status_detail = f"Radio sender error: {e}"
            return None

        with self.process_lock:
            self.send_proc = proc

        stop_event = threading.Event()
        threading.Thread(target=self.relay_stream_data,
                         args=(proc, self.current_stdin, stop_event), daemon=True).start()
        threading.Thread(target=self.watch_send_proc,
                         args=(proc, stop_event), daemon=True).start()
        return stop_event

    def play_video(self, video_info, seek_seconds=0):
        url = video_info.get("url", "")
        is_local = bool(video_info.get("is_local") or video_info.get("type") == "local_video" or (video_info.get("path") and os.path.exists(video_info["path"])))
        try:
            if is_local:
                video_url = os.path.abspath(video_info.get("path") or url)
                audio_url = None
                title = video_info.get("title") or os.path.splitext(os.path.basename(video_url))[0]
                duration = video_info.get("duration", 0)
                if not duration:
                    duration = get_video_file_duration(video_url)
                headers = None
                log_print(f"[Player] Using local video file: {title} ({video_url})")
            else:
                cached = None
                with self.prefetch_lock:
                    if url in self.prefetch_cache and not self.prefetch_cache[url].get("is_radio"):
                        c = self.prefetch_cache.pop(url)
                        if time.time() - c.get("timestamp", 0) < 600:
                            cached = c

                if cached:
                    video_url = cached["video_url"]
                    audio_url = cached["audio_url"]
                    title = cached["title"]
                    duration = cached["duration"]
                    headers = cached["headers"]
                    log_print(f"[Player] Using pre-fetched stream URLs for: {title}")
                else:
                    video_url, audio_url, title, duration, headers = self.get_stream_urls(url)

            self.current_video = {
                "title": title,
                "url": url,
                "duration": duration
            }
            self.current_video_start_time = time.time() - max(0, seek_seconds)
            log_print(f"[Player] Now Playing: {title} (seek: {int(seek_seconds)}s, pts_offset: {self.accumulated_pts:.2f}s)")
        except Exception as e:
            log_print(f"[Player] Failed to get stream URL: {e}")
            self.current_video = {"title": f"Failed: {video_info.get('title', 'Unknown')}", "url": url, "duration": 0}
            self.status = "error"
            self.status_detail = "Failed to load stream"
            return None

        # 受信側FFmpegが未起動/停止時のみ起動（ストリームの連続性を維持）
        if not self.ensure_hls_receiver():
            self.current_video = {"title": "FFmpeg Error (Check PATH)", "url": url, "duration": 0}
            self.status = "error"
            self.status_detail = "FFmpeg Error"
            return None

        headers_str = ""
        if headers:
            headers_str = "".join(f"{k}: {v}\r\n" for k, v in headers.items())

        input_opts = []
        if not is_local:
            input_opts.extend([
                "-reconnect", "1",
                "-reconnect_streamed", "1",
                "-reconnect_delay_max", "2",
                "-reconnect_on_network_error", "1",
                "-reconnect_on_http_error", "4xx,5xx",
                "-rw_timeout", "10000000",
            ])
            if headers_str:
                input_opts.extend(["-headers", headers_str])
        if seek_seconds > 0:
            input_opts.extend(["-ss", str(int(seek_seconds))])

        overlay_video = bool(self.config.get("overlay_qr_enabled", False) or self.config.get("overlay_qr_video", False))
        qr_overlay_file = self.generate_qr_overlay_image() if overlay_video else None

        clock_video = bool(self.config.get("overlay_clock_enabled", False) or self.config.get("overlay_clock_video", False))
        has_clock = bool(clock_video)
        clock_filter = get_clock_filter_for_config(self.config) if has_clock else None

        cmd = [get_ffmpeg_cmd(), "-fflags", "+genpts"]
        if self.accumulated_pts > 0:
            cmd.extend(["-output_ts_offset", f"{self.accumulated_pts:.3f}"])
        cmd.extend(input_opts)
        cmd.extend(["-i", video_url])
        if audio_url:
            cmd.extend(input_opts)
            cmd.extend(["-i", audio_url])

        has_qr = bool(overlay_video and qr_overlay_file and os.path.exists(qr_overlay_file))
        has_clock = bool(clock_video)

        if has_qr or has_clock or is_local:
            if has_qr:
                qr_idx = 2 if audio_url else 1
                cmd.extend(["-loop", "1", "-i", os.path.abspath(qr_overlay_file)])
                mode = self.config.get("overlay_qr_mode", "bottom-right")
            else:
                qr_idx = 0
                mode = "bottom-right"

            overlay_filter = self._build_video_filter_complex(has_qr, has_clock, qr_idx, mode, clock_filter)

            if overlay_filter:
                cmd.extend([
                    "-filter_complex", overlay_filter,
                    "-map", "[vout]"
                ])
            else:
                cmd.extend(["-map", "0:v:0"])
            if audio_url:
                cmd.extend(["-map", "1:a:0"])
            else:
                cmd.extend(["-map", "0:a:0?"])
            cmd.extend([
                "-c:v", "libx264",
                "-preset", "ultrafast",
                "-tune", "zerolatency",
                "-profile:v", "baseline",
                "-level", "3.1",
                "-pix_fmt", "yuv420p",
                "-g", "60",
                "-keyint_min", "60",
                "-b:v", "2500k",
                "-maxrate", "3000k",
                "-bufsize", "2000k",
                "-c:a", "aac", "-b:a", "128k",
                "-af", "aresample=async=1",
                "-shortest",
                "-f", "mpegts", "pipe:1"
            ])
        else:
            cmd.extend(["-map", "0:v:0"])
            if audio_url:
                cmd.extend(["-map", "1:a:0"])
            else:
                cmd.extend(["-map", "0:a:0?"])
            cmd.extend(["-c:v", "copy", "-c:a", "aac", "-b:a", "128k",
                        "-af", "aresample=async=1", "-shortest", "-f", "mpegts", "pipe:1"])

        try:
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, bufsize=0,
                creationflags=CREATE_NO_WINDOW
            )
        except Exception as e:
            log_print(f"[Player] Error starting FFmpeg sender: {e}")
            self.status = "error"
            self.status_detail = f"FFmpeg sender error: {e}"
            return None

        with self.process_lock:
            self.send_proc = proc

        stop_event = threading.Event()
        threading.Thread(target=self.relay_stream_data,
                         args=(proc, self.current_stdin, stop_event), daemon=True).start()
        threading.Thread(target=self.watch_send_proc,
                         args=(proc, stop_event), daemon=True).start()
        return stop_event

    _stream_video = play_video

    def _build_video_filter_complex(self, has_qr, has_clock, qr_idx, qr_mode, clock_filter):
        """QR/時計オーバーレイ用 -filter_complex 文字列を安全に構築（動画・ラジオ共通）"""
        if has_qr:
            if qr_mode == "fullscreen":
                base = f"[{qr_idx}:v][0:v]scale2ref[qr_scaled][vmain];[vmain][qr_scaled]overlay=0:0:shortest=1"
            else:
                base = f"[0:v][{qr_idx}:v]overlay=main_w-overlay_w-25:main_h-overlay_h-25:shortest=1"

            if has_clock:
                return base + f"[v_qr];[v_qr]{clock_filter}[vout]"
            else:
                return base + "[vout]"
        elif has_clock:
            return f"[0:v]{clock_filter}[vout]"
        return None

    def optimize_image_to_cache(self, img_input, output_filename=None):
        """PIL画像、バイナリ、またはファイルパスから 1920x1080 黒帯付き最適化画像を生成して保存"""
        os.makedirs(IMAGE_CACHE_DIR, exist_ok=True)
        if not output_filename:
            output_filename = f"photo_{int(time.time())}_{random.randint(1000, 9999)}.png"
        output_path = os.path.join(IMAGE_CACHE_DIR, output_filename)

        try:
            if isinstance(img_input, str):
                img = Image.open(img_input)
            elif isinstance(img_input, (bytes, bytearray)):
                img = Image.open(io.BytesIO(img_input))
            elif isinstance(img_input, Image.Image):
                img = img_input
            else:
                return None

            # EXIF回転補正
            img = ImageOps.exif_transpose(img)

            # RGBモードに変換
            if img.mode != "RGB":
                img = img.convert("RGBA")
                canvas = Image.new("RGBA", img.size, (0, 0, 0, 255))
                img = Image.alpha_composite(canvas, img).convert("RGB")

            # 1920x1080 (16:9) 黒背景にアスペクト比維持でレターボックス配置
            target_w, target_h = 1920, 1080
            src_w, src_h = img.size

            ratio = min(target_w / src_w, target_h / src_h)
            new_w = max(1, int(src_w * ratio))
            new_h = max(1, int(src_h * ratio))

            img_resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

            final_img = Image.new("RGB", (target_w, target_h), (0, 0, 0))
            offset_x = (target_w - new_w) // 2
            offset_y = (target_h - new_h) // 2
            final_img.paste(img_resized, (offset_x, offset_y))

            final_img.save(output_path, "PNG")
            return output_path
        except Exception as e:
            log_print(f"[Core] Error optimizing image: {e}")
            return None

    def add_video_file(self, file_path, title=None, original_filename=None, is_uploaded=False):
        """ローカル動画ファイルを動画キュー (play_queue) に追加"""
        with self.queue_lock:
            if len(self.play_queue) >= MAX_QUEUE_CAPACITY:
                log_print(f"[Core] Queue capacity reached ({MAX_QUEUE_CAPACITY}).")
                return None

        if not os.path.exists(file_path):
            log_print(f"[Core] Video file not found: {file_path}")
            return None

        clean_orig = original_filename or os.path.basename(file_path)
        if not title:
            base_name = os.path.splitext(clean_orig)[0]
            title = f"🎬 {base_name}" if not base_name.startswith("🎬") else base_name

        duration = get_video_file_duration(file_path)
        video_id = f"v_{uuid.uuid4().hex[:8]}"
        item = {
            "id": video_id,
            "type": "local_video",
            "title": title,
            "url": os.path.abspath(file_path),
            "path": os.path.abspath(file_path),
            "original_filename": clean_orig,
            "duration": duration,
            "is_local": True,
            "is_uploaded": is_uploaded
        }
        with self.queue_lock:
            self.play_queue.append(item)
        log_print(f"[Core] Added local video to queue: {title} (id: {video_id}, {duration:.1f}s)")
        return item

    def add_video_bytes(self, video_bytes, original_filename="video.mp4"):
        """アップロードされた動画バイナリを videos フォルダに保存してキューに追加"""
        with self.queue_lock:
            if len(self.play_queue) >= MAX_QUEUE_CAPACITY:
                log_print(f"[Core] Queue capacity reached ({MAX_QUEUE_CAPACITY}).")
                return None

        os.makedirs(VIDEO_STORAGE_DIR, exist_ok=True)
        ext = os.path.splitext(original_filename)[1].lower()
        if ext not in (".mp4", ".mov", ".webm", ".mkv", ".avi", ".m4v", ".ts", ".flv"):
            ext = ".mp4"
        saved_filename = f"upload_{int(time.time())}_{uuid.uuid4().hex[:6]}{ext}"
        saved_path = os.path.join(VIDEO_STORAGE_DIR, saved_filename)

        try:
            with open(saved_path, "wb") as f:
                f.write(video_bytes)
        except Exception as e:
            log_print(f"[Core] Failed to save uploaded video file: {e}")
            return None

        return self.add_video_file(saved_path, original_filename=original_filename, is_uploaded=True)

    def add_image_file(self, file_path, title=None):
        """ローカル画像ファイルを最適化して写真プールに追加"""
        with self.photo_lock:
            if len(self.photo_pool) >= MAX_PHOTO_CAPACITY:
                log_print(f"[Core] Photo pool capacity reached ({MAX_PHOTO_CAPACITY}).")
                return None

        cached_path = self.optimize_image_to_cache(file_path)
        if not cached_path:
            return None

        if not title:
            title = os.path.splitext(os.path.basename(file_path))[0]

        duration = int(self.config.get("image_display_duration", 15))
        photo_id = f"p_{uuid.uuid4().hex[:8]}"
        item = {
            "id": photo_id,
            "type": "image",
            "title": f"🖼 {title}",
            "url": os.path.basename(cached_path),
            "path": cached_path,
            "original_filename": os.path.basename(file_path),
            "duration": duration
        }
        with self.photo_lock:
            self.photo_pool.append(item)
        log_print(f"[Core] Added photo to pool: {title} (id: {photo_id}, {duration}s)")
        self.reload_stream_event.set()
        return item

    def add_image_bytes(self, image_bytes, original_filename="photo.jpg"):
        """アップロードされた画像バイナリを最適化して写真プールに追加"""
        with self.photo_lock:
            if len(self.photo_pool) >= MAX_PHOTO_CAPACITY:
                log_print(f"[Core] Photo pool capacity reached ({MAX_PHOTO_CAPACITY}).")
                return None

        cached_path = self.optimize_image_to_cache(image_bytes)
        if not cached_path:
            return None

        title = os.path.splitext(os.path.basename(original_filename))[0] or "Uploaded Photo"
        duration = int(self.config.get("image_display_duration", 15))
        photo_id = f"p_{uuid.uuid4().hex[:8]}"
        item = {
            "id": photo_id,
            "type": "image",
            "title": f"🖼 {title}",
            "url": os.path.basename(cached_path),
            "path": cached_path,
            "original_filename": original_filename,
            "duration": duration
        }
        with self.photo_lock:
            self.photo_pool.append(item)
        log_print(f"[Core] Added uploaded photo to pool: {title} (id: {photo_id}, {duration}s)")
        self.reload_stream_event.set()
        return item

    def get_photos(self):
        """写真プール内の有効な写真一覧を取得"""
        with self.photo_lock:
            valid = []
            for p in self.photo_pool:
                if p.get("path") and os.path.exists(p["path"]):
                    valid.append(dict(p))
            return valid

    def remove_photo(self, photo_id_or_idx):
        """写真プールから特定の写真を削除（キャッシュファイルも削除）"""
        with self.photo_lock:
            target_idx = None
            if isinstance(photo_id_or_idx, int):
                if 0 <= photo_id_or_idx < len(self.photo_pool):
                    target_idx = photo_id_or_idx
            elif isinstance(photo_id_or_idx, str):
                for idx, p in enumerate(self.photo_pool):
                    if p.get("id") == photo_id_or_idx or p.get("url") == photo_id_or_idx or p.get("path") == photo_id_or_idx:
                        target_idx = idx
                        break
            if target_idx is not None:
                removed = self.photo_pool.pop(target_idx)
                if removed.get("path") and os.path.exists(removed["path"]):
                    try:
                        os.remove(removed["path"])
                    except Exception:
                        pass
                log_print(f"[Core] Removed photo from pool: {removed.get('title')}")
                self.reload_stream_event.set()
                return True
            return False

    def move_photo(self, from_idx: int, to_idx: int):
        """写真プール内の写真の順序を入れ替え"""
        with self.photo_lock:
            if 0 <= from_idx < len(self.photo_pool) and 0 <= to_idx < len(self.photo_pool):
                item = self.photo_pool.pop(from_idx)
                self.photo_pool.insert(to_idx, item)
                log_print(f"[Core] Moved photo in pool from {from_idx} to {to_idx}")
                return True
            return False

    def clear_photos(self):
        """写真プール内の全写真を削除"""
        with self.photo_lock:
            for p in self.photo_pool:
                if p.get("path") and os.path.exists(p["path"]):
                    try:
                        os.remove(p["path"])
                    except Exception:
                        pass
            self.photo_pool.clear()
            self.slideshow_index = 0
            log_print("[Core] Cleared all photos from photo pool.")
            self.reload_stream_event.set()
            return True

    def play_image(self, image_info):
        """最適化済み静止画像をFFmpegネイティブでHLS配信（安全・低遅延）"""
        image_path = image_info.get("path")
        if not image_path or not os.path.exists(image_path):
            log_print(f"[Player] Image file not found: {image_path}")
            self.current_video = {"title": "Image not found", "url": "", "duration": 0, "type": "image"}
            self.status = "error"
            self.status_detail = "Image file not found"
            return None

        # QRオーバーレイが有効な場合はQR合成済み画像パスを取得
        playback_image_path = self.get_image_for_playback(image_path)

        if not self.ensure_hls_receiver():
            self.current_video = {"title": "FFmpeg Error", "url": "", "duration": 0, "type": "image"}
            self.status = "error"
            self.status_detail = "FFmpeg Error"
            return None

        clock_video = bool(self.config.get("overlay_clock_enabled", False) or self.config.get("overlay_clock_video", False))
        has_clock = bool(clock_video)
        clock_filter = get_clock_filter_for_config(self.config) if has_clock else None

        cmd = [
            get_ffmpeg_cmd(), "-re",
        ]
        if self.accumulated_pts > 0:
            cmd.extend(["-output_ts_offset", f"{self.accumulated_pts:.3f}"])
        cmd.extend([
            "-loop", "1", "-i", os.path.abspath(playback_image_path),
            "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
        ])
        if has_clock and clock_filter:
            cmd.extend(["-vf", clock_filter])
        cmd.extend([
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-tune", "zerolatency",
            "-profile:v", "baseline",
            "-level", "3.1",
            "-bf", "0",
            "-g", "30",
            "-keyint_min", "30",
            "-sc_threshold", "0",
            "-pix_fmt", "yuv420p",
            "-r", "30",
            "-b:v", "1500k",
            "-maxrate", "1500k",
            "-bufsize", "1000k",
            "-c:a", "aac", "-b:a", "64k",
            "-fflags", "+nobuffer+flush_packets",
            "-flush_packets", "1",
            "-muxdelay", "0",
            "-muxpreload", "0",
            "-f", "mpegts", "pipe:1"
        ])

        try:
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, bufsize=0,
                creationflags=CREATE_NO_WINDOW
            )
        except Exception as e:
            log_print(f"[Player] Error starting Photo sender: {e}")
            self.status = "error"
            self.status_detail = f"Photo sender error: {e}"
            return None

        with self.process_lock:
            self.send_proc = proc

        stop_event = threading.Event()
        threading.Thread(target=self.relay_stream_data,
                         args=(proc, self.current_stdin, stop_event, False), daemon=True).start()
        threading.Thread(target=self.watch_send_proc,
                         args=(proc, stop_event), daemon=True).start()
        return stop_event

    def add_to_queue(self, url):
        """URL（動画または画像）またはローカルファイルパスを解析してキューに追加"""
        with self.queue_lock:
            if len(self.play_queue) >= MAX_QUEUE_CAPACITY:
                log_print(f"[Core] Cannot add items: Queue reached max capacity ({MAX_QUEUE_CAPACITY}).")
                return []

        # ローカル動画ファイルの場合
        if is_video_url_or_file(url) and os.path.exists(url):
            item = self.add_video_file(url)
            return [item] if item else []

        # 画像URLまたはローカル画像ファイルの場合
        if is_image_url_or_file(url):
            if os.path.exists(url):
                item = self.add_image_file(url)
                return [item] if item else []
            is_safe, reason = is_safe_url(url)
            if not is_safe:
                log_print(f"[Core] Rejected unsafe image URL: {reason}")
                return []
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    img_bytes = resp.read(10 * 1024 * 1024) # max 10MB
                filename = url.split("/")[-1].split("?")[0] or "web_photo.png"
                item = self.add_image_bytes(img_bytes, filename)
                return [item] if item else []
            except Exception as e:
                log_print(f"[Core] Failed to fetch image URL: {e}")
                return []

        items = self.expand_playlist(url)
        if items:
            with self.queue_lock:
                available_space = max(0, MAX_QUEUE_CAPACITY - len(self.play_queue))
                items_to_add = items[:available_space]
                self.play_queue.extend(items_to_add)
            log_print(f"[Core] Added {len(items_to_add)} items to queue.")
            return items_to_add
        return []

    def skip(self):
        log_print("[Player] Skip requested.")
        self.skip_event.set()
        self.video_done_event.set()
        with self.process_lock:
            proc = self.send_proc
        if proc:
            kill_proc(proc)

    def clear_queue(self):
        with self.queue_lock:
            for item in self.play_queue:
                if item.get("is_uploaded") and item.get("path") and os.path.exists(item["path"]):
                    try:
                        os.remove(item["path"])
                    except Exception:
                        pass
            self.play_queue.clear()
        log_print("[Core] Queue cleared.")

    def delete_queue_item(self, idx):
        with self.queue_lock:
            if 0 <= idx < len(self.play_queue):
                removed = self.play_queue.pop(idx)
                if removed.get("is_uploaded") and removed.get("path") and os.path.exists(removed["path"]):
                    try:
                        os.remove(removed["path"])
                    except Exception:
                        pass
                log_print(f"[Core] Removed item at index {idx} ({removed.get('title')}) from queue.")
                return removed
        return None

    def move_queue_item(self, from_idx, to_idx):
        with self.queue_lock:
            if 0 <= from_idx < len(self.play_queue) and 0 <= to_idx < len(self.play_queue):
                item = self.play_queue.pop(from_idx)
                self.play_queue.insert(to_idx, item)
                return True
        return False

    def generate_qr_overlay_image(self):
        """動画・写真ストリーム上に重ねて表示するQRコードカード (RGBA) を生成（右下コンパクト/フル画面）"""
        is_tunnel_ready = bool(self.tunnel_raw_url and "trycloudflare.com" in self.tunnel_raw_url)
        is_tunnel_enabled = getattr(self, "enable_tunnel", True)
        port = self.config.get("port", 8000)
        url = self.tunnel_raw_url if is_tunnel_ready else f"http://{get_local_ip()}:{port}"
        mode = self.config.get("overlay_qr_mode", "bottom-right")

        try:
            if mode == "fullscreen":
                # --- フル画面オーバーレイモード (1920x1080 半透明ダーク) ---
                width, height = 1920, 1080
                img = Image.new("RGBA", (width, height), color=(15, 23, 42, 225)) # 半透明ダークスレート
                draw = ImageDraw.Draw(img)

                draw.rectangle([(0, 0), (width, 90)], fill=(30, 41, 59, 240))
                draw.rectangle([(0, height - 70), (width, height)], fill=(30, 41, 59, 240))

                try:
                    font_title = ImageFont.truetype("arial.ttf", 52)
                    font_sub = ImageFont.truetype("arial.ttf", 30)
                    font_url = ImageFont.truetype("arial.ttf", 34)
                    font_info = ImageFont.truetype("arial.ttf", 24)
                except Exception:
                    font_title = font_sub = font_url = font_info = ImageFont.load_default()

                draw.text((width // 2, 45), "VRC_Media_Streamer", fill=(56, 189, 248, 255), anchor="mm", font=font_title)
                draw.text((width // 2, 140), "Scan QR code or visit URL below to request YouTube videos!", fill=(226, 232, 240, 255), anchor="mm", font=font_sub)

                qr = qrcode.QRCode(
                    version=1,
                    error_correction=qrcode.constants.ERROR_CORRECT_M,
                    box_size=12,
                    border=2,
                )
                qr.add_data(url)
                qr.make(fit=True)
                qr_img = qr.make_image(fill_color="#0F172A", back_color="#FFFFFF").convert("RGBA")

                qr_w, qr_h = qr_img.size
                qr_x = (width - qr_w) // 2
                qr_y = (height - qr_h) // 2 - 15

                card_pad = 22
                draw.rectangle(
                    [(qr_x - card_pad, qr_y - card_pad), (qr_x + qr_w + card_pad, qr_y + qr_h + card_pad)],
                    fill=(255, 255, 255, 255)
                )
                img.paste(qr_img, (qr_x, qr_y), qr_img)

                url_box_y = height - 160
                draw.text((width // 2, url_box_y), f"Web Request URL: {url}", fill=(248, 250, 252, 255), anchor="mm", font=font_url)
                draw.text((width // 2, url_box_y + 45), "Scan this QR code with your phone or visit the URL directly.", fill=(148, 163, 184, 255), anchor="mm", font=font_info)
                draw.text((width // 2, height - 35), "VRChat YouTube Streamer • Powered by yt-dlp & FFmpeg", fill=(100, 116, 139, 255), anchor="mm", font=font_info)

                img.save(QR_OVERLAY_PATH, "PNG")
                return QR_OVERLAY_PATH

            else:
                # --- 右下コンパクトモード (白角丸カード: QRコード + 完全URL併記) ---
                qr = qrcode.QRCode(
                    version=1,
                    error_correction=qrcode.constants.ERROR_CORRECT_M,
                    box_size=5,
                    border=1,
                )
                qr.add_data(url)
                qr.make(fit=True)
                qr_img = qr.make_image(fill_color="#0F172A", back_color="#FFFFFF").convert("RGBA")

                qr_w, qr_h = qr_img.size # 約 150x150
                card_w = max(260, qr_w + 30)
                card_h = qr_h + 85 # QR + ラベル + URLテキスト用の高さを確保

                card = Image.new("RGBA", (card_w, card_h), (0, 0, 0, 0))
                draw = ImageDraw.Draw(card)

                # 角丸白カード (高い視認性を保ちつつアルファブレンド)
                radius = 12
                draw.rounded_rectangle(
                    [(0, 0), (card_w - 1, card_h - 1)],
                    radius=radius,
                    fill=(255, 255, 255, 245),
                    outline=(203, 213, 225, 245),
                    width=2
                )

                # QRコードを上部中央に配置
                qr_x = (card_w - qr_w) // 2
                card.paste(qr_img, (qr_x, 12), qr_img)

                # 下部にURLと案内を完全表記（手入力可能）
                try:
                    font_lbl = ImageFont.truetype("arial.ttf", 11)
                    font_size = 12 if len(url) <= 32 else (11 if len(url) <= 36 else 10)
                    font_url = ImageFont.truetype("arial.ttf", font_size)
                except Exception:
                    font_lbl = font_url = ImageFont.load_default()

                # ラベル「Request via QR or URL:」
                draw.text((card_w // 2, qr_h + 24), "Request via QR or URL:", fill=(100, 116, 139, 255), anchor="mm", font=font_lbl)

                # 完全なURL（手入力できるよう省略なし）
                draw.text((card_w // 2, qr_h + 46), url, fill=(15, 23, 42, 255), anchor="mm", font=font_url)

                card.save(QR_OVERLAY_PATH, "PNG")
                return QR_OVERLAY_PATH
        except Exception as e:
            log_print(f"[Core] Error generating QR overlay image: {e}")
            return None

    def get_image_for_playback(self, image_path, unique_id=None):
        """写真・スライドショー再生用: 1920x1080に正規化し、QR/URL設定に応じてオーバーレイを合成した画像パスを返す"""
        if not image_path or not os.path.exists(image_path):
            return image_path

        overlay_enabled = bool(self.config.get("overlay_qr_enabled", False) or self.config.get("overlay_qr_image", False))
        qr_path = self.generate_qr_overlay_image() if overlay_enabled else None
        has_qr = bool(qr_path and os.path.exists(qr_path))

        # キャッシュキーは「元画像 + 合成するオーバーレイの内容」だけで決まる安定値にする。
        # 以前は呼び出し側の連番 unique_id をキーに混ぜていたため、シャッフル有効時は
        # 曲が変わるたびに同じ写真が別名で再生成され、1曲ごとに写真枚数ぶんの
        # リサイズ＋PNG保存（200枚なら数十秒）が走って送信再開が遅れ、
        # さらにキャッシュファイルが際限なく増え続けていた。
        try:
            src_stat = os.stat(image_path)
            key_parts = [os.path.abspath(image_path), str(int(src_stat.st_mtime)), str(src_stat.st_size),
                         str(overlay_enabled)]
        except OSError:
            key_parts = [os.path.abspath(image_path), str(overlay_enabled)]
        if has_qr:
            try:
                qr_stat = os.stat(qr_path)
                # QRの内容（URL）が変わればキャッシュも作り直す
                key_parts.append(f"{int(qr_stat.st_mtime)}_{qr_stat.st_size}")
            except OSError:
                pass
            key_parts.append(str(self.config.get("overlay_qr_mode", "bottom-right")))
        path_hash = hashlib.md5("_".join(key_parts).encode()).hexdigest()[:12]
        temp_path = os.path.join(IMAGE_CACHE_DIR, f"playback_prep_{path_hash}.png")
        try:
            if os.path.exists(temp_path) and os.path.getsize(temp_path) > 0:
                return temp_path
        except OSError:
            pass

        try:
            # 1. 元画像を読み込み、EXIFの向きを補正
            src_img = Image.open(image_path)
            src_img = ImageOps.exif_transpose(src_img)
            if src_img.mode != "RGB":
                src_img = src_img.convert("RGBA")

            # 2. 1920x1080 キャンバスにアスペクト比を維持してレターボックス配置
            target_w, target_h = 1920, 1080
            src_w, src_h = src_img.size
            ratio = min(target_w / src_w, target_h / src_h)
            new_w = max(1, int(src_w * ratio))
            new_h = max(1, int(src_h * ratio))

            img_resized = src_img.resize((new_w, new_h), Image.Resampling.LANCZOS)
            canvas = Image.new("RGBA", (target_w, target_h), (0, 0, 0, 255))
            offset_x = (target_w - new_w) // 2
            offset_y = (target_h - new_h) // 2

            if img_resized.mode == "RGBA":
                canvas.paste(img_resized, (offset_x, offset_y), img_resized)
            else:
                canvas.paste(img_resized, (offset_x, offset_y))

            # 3. QRコード・URLカードのオーバーレイ合成（有効な場合）
            if has_qr:
                qr_img = Image.open(qr_path).convert("RGBA")
                qw, qh = qr_img.size
                mode = self.config.get("overlay_qr_mode", "bottom-right")

                if mode == "fullscreen":
                    canvas.alpha_composite(qr_img, dest=(0, 0))
                else:
                    pos_x = max(0, target_w - qw - 25)
                    pos_y = max(0, target_h - qh - 25)
                    canvas.alpha_composite(qr_img, dest=(pos_x, pos_y))

            # 4. キャッシュファイルとして保存。
            # 配信中のFFmpegが concat マニフェスト経由で同じパスを読み直すため、
            # 書きかけのファイルを掴ませないよう一時名で書いてから置換する。
            os.makedirs(IMAGE_CACHE_DIR, exist_ok=True)
            tmp_write_path = f"{temp_path}.{uuid.uuid4().hex[:6]}.part"
            canvas.convert("RGB").save(tmp_write_path, "PNG")
            os.replace(tmp_write_path, temp_path)
            return temp_path
        except Exception as e:
            log_print(f"[Core] Failed to prepare playback image ({image_path}): {e}")
            return image_path

    def _draw_notice_banner(self, img, text):
        """画像の下部に案内バー（半透明ダーク帯＋スカイブルー枠＋テキスト）を合成"""
        try:
            overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
            draw = ImageDraw.Draw(overlay)
            w, h = img.size
            bar_y1 = h - 130
            bar_y2 = h - 50
            draw.rounded_rectangle(
                [(60, bar_y1), (w - 60, bar_y2)],
                radius=14,
                fill=(15, 23, 42, 230),
                outline=(56, 189, 248, 220),
                width=2
            )
            font_notice = get_pil_font(28, bold=True)
            draw.text((w // 2, (bar_y1 + bar_y2) // 2), text, fill="#F8FAFC", anchor="mm", font=font_notice)

            canvas = img.convert("RGBA")
            combined = Image.alpha_composite(canvas, overlay)
            return combined.convert("RGB")
        except Exception as e:
            log_print(f"[Core] Error drawing notice banner: {e}")
            return img

    def generate_standby_image(self, notice_text=None):
        """待機用画面（固定画像またはQRコード & URL付き 1920x1080）を生成して保存"""
        standby_mode = self.config.get("standby_mode", "image")

        if standby_mode == "image":
            # ==================== 固定画像モード (デフォルト) ====================
            custom_path = self.config.get("standby_image_path", "")
            target_image_path = None
            if custom_path and os.path.exists(custom_path):
                target_image_path = custom_path
            elif os.path.exists(DEFAULT_STANDBY_IMAGE_PATH):
                target_image_path = DEFAULT_STANDBY_IMAGE_PATH

            if target_image_path:
                try:
                    img = Image.open(target_image_path)
                    img = ImageOps.exif_transpose(img)
                    if img.mode != "RGB":
                        img = img.convert("RGBA")
                        canvas = Image.new("RGBA", img.size, (0, 0, 0, 255))
                        img = Image.alpha_composite(canvas, img).convert("RGB")

                    target_w, target_h = 1920, 1080
                    src_w, src_h = img.size
                    ratio = min(target_w / src_w, target_h / src_h)
                    new_w = max(1, int(src_w * ratio))
                    new_h = max(1, int(src_h * ratio))

                    img_resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
                    final_img = Image.new("RGB", (target_w, target_h), (0, 0, 0))
                    offset_x = (target_w - new_w) // 2
                    offset_y = (target_h - new_h) // 2
                    final_img.paste(img_resized, (offset_x, offset_y))

                    # overlay_qr_enabled なら QR オーバーレイを合成 (v2.6.0 standby_mode 追加時の考慮漏れ修正)
                    if bool(self.config.get("overlay_qr_enabled", False)):
                        qr_path = self.generate_qr_overlay_image()
                        if qr_path and os.path.exists(qr_path):
                            try:
                                qr_img = Image.open(qr_path).convert("RGBA")
                                canvas = final_img.convert("RGBA")
                                qr_mode = self.config.get("overlay_qr_mode", "bottom-right")
                                if qr_mode == "fullscreen":
                                    canvas.alpha_composite(qr_img, dest=(0, 0))
                                else:
                                    qw, qh = qr_img.size
                                    pos_x = max(0, target_w - qw - 25)
                                    pos_y = max(0, target_h - qh - 25)
                                    canvas.alpha_composite(qr_img, dest=(pos_x, pos_y))
                                final_img = canvas.convert("RGB")
                            except Exception as e:
                                log_print(f"[Core] Error compositing QR overlay on standby image: {e}")

                    if notice_text:
                        final_img = self._draw_notice_banner(final_img, notice_text)

                    final_img.save(STANDBY_IMAGE_PATH, "PNG")
                    return
                except Exception as e:
                    log_print(f"[Core] Error rendering custom standby image ({target_image_path}): {e}")

            # フォールバック (画像が開けない場合、シンプルな待機画面を生成)
            img = Image.new("RGB", (1920, 1080), color="#0F172A")
            draw = ImageDraw.Draw(img)
            font_title = get_pil_font(52, bold=True)
            font_sub = get_pil_font(30, bold=False)
            draw.text((960, 480), "VRC_Media_Streamer", fill="#38BDF8", anchor="mm", font=font_title)
            draw.text((960, 560), "Standby — Queue is Empty", fill="#94A3B8", anchor="mm", font=font_sub)
            # overlay_qr_enabled なら QR オーバーレイを合成
            if bool(self.config.get("overlay_qr_enabled", False)):
                qr_path = self.generate_qr_overlay_image()
                if qr_path and os.path.exists(qr_path):
                    try:
                        qr_img = Image.open(qr_path).convert("RGBA")
                        canvas = img.convert("RGBA")
                        qr_mode = self.config.get("overlay_qr_mode", "bottom-right")
                        if qr_mode == "fullscreen":
                            canvas.alpha_composite(qr_img, dest=(0, 0))
                        else:
                            qw, qh = qr_img.size
                            pos_x = max(0, 1920 - qw - 25)
                            pos_y = max(0, 1080 - qh - 25)
                            canvas.alpha_composite(qr_img, dest=(pos_x, pos_y))
                        img = canvas.convert("RGB")
                    except Exception as e:
                        log_print(f"[Core] Error compositing QR overlay on fallback standby: {e}")

            if notice_text:
                img = self._draw_notice_banner(img, notice_text)

            try:
                img.save(STANDBY_IMAGE_PATH, "PNG")
            except Exception as e:
                log_print(f"[Core] Failed to save fallback standby image: {e}")
            return

        # ==================== QRコード & URL 案内画面モード ====================
        is_tunnel_ready = bool(self.tunnel_raw_url and "trycloudflare.com" in self.tunnel_raw_url)
        is_tunnel_enabled = getattr(self, "enable_tunnel", True)
        port = self.config.get("port", 8000)
        url = self.tunnel_raw_url if is_tunnel_ready else (f"http://{get_local_ip()}:{port}" if not is_tunnel_enabled else f"http://localhost:{port}")
        mode = self.config.get("overlay_qr_mode", "bottom-right")

        width, height = 1920, 1080
        img = Image.new("RGB", (width, height), color="#0F172A") # Dark slate
        draw = ImageDraw.Draw(img)

        # 1. Background accents
        draw.rectangle([(0, 0), (width, 90)], fill="#1E293B")
        draw.rectangle([(0, height - 70), (width, height)], fill="#1E293B")

        font_title = get_pil_font(52, bold=True)
        font_head = get_pil_font(44, bold=True)
        font_sub = get_pil_font(30, bold=False)
        font_url = get_pil_font(34, bold=True)
        font_info = get_pil_font(24, bold=False)
        font_card_url = get_pil_font(16, bold=False)
        font_footer = get_pil_font(22, bold=False)

        draw.text((width // 2, 45), "VRC_Media_Streamer", fill="#38BDF8", anchor="mm", font=font_title)

        if mode == "fullscreen":
            # ==================== フル画面モード (中央大画面QR) ====================
            if is_tunnel_ready:
                draw.text((width // 2, 140), "Queue is Empty — Request a video from your smartphone or browser!", fill="#94A3B8", anchor="mm", font=font_sub)
            elif not is_tunnel_enabled:
                draw.text((width // 2, 140), f"Local Test Mode (http://localhost:{port}) — Add videos via Web!", fill="#34D399", anchor="mm", font=font_sub)
            else:
                draw.text((width // 2, 140), "Connecting to Cloudflare Tunnel... Please wait a moment.", fill="#F59E0B", anchor="mm", font=font_sub)

            try:
                qr = qrcode.QRCode(
                    version=1,
                    error_correction=qrcode.constants.ERROR_CORRECT_M,
                    box_size=12,
                    border=2,
                )
                qr.add_data(url)
                qr.make(fit=True)
                qr_img = qr.make_image(fill_color="#0F172A", back_color="#FFFFFF").convert("RGB")
                
                qr_w, qr_h = qr_img.size
                qr_x = (width - qr_w) // 2
                qr_y = (height - qr_h) // 2 - 15

                card_pad = 22
                draw.rectangle(
                    [(qr_x - card_pad, qr_y - card_pad), (qr_x + qr_w + card_pad, qr_y + qr_h + card_pad)],
                    fill="#FFFFFF"
                )
                img.paste(qr_img, (qr_x, qr_y))
            except Exception as e:
                log_print(f"[Core] Error generating QR code: {e}")

            url_box_y = height - 160
            if is_tunnel_ready:
                draw.text((width // 2, url_box_y), f"Web Request URL: {url}", fill="#F8FAFC", anchor="mm", font=font_url)
                draw.text((width // 2, url_box_y + 45), "Scan this QR code with your phone or visit the URL to add YouTube videos to the queue.", fill="#64748B", anchor="mm", font=font_info)
            elif not is_tunnel_enabled:
                draw.text((width // 2, url_box_y), f"Local Stream URL: {url}/stream.m3u8", fill="#38BDF8", anchor="mm", font=font_url)
                draw.text((width // 2, url_box_y + 45), f"Open {url} in your PC browser to request videos locally.", fill="#64748B", anchor="mm", font=font_info)
            else:
                draw.text((width // 2, url_box_y), "Public URL will appear here once connected...", fill="#94A3B8", anchor="mm", font=font_url)
                draw.text((width // 2, url_box_y + 45), "Establishing secure tunnel to Cloudflare network.", fill="#64748B", anchor="mm", font=font_info)

        else:
            # ==================== 右下コンパクトモード (右下に小さく配置) ====================
            # 画面左側〜中央: リクエスト手順と案内
            draw.text((120, 260), "Now Idle • Queue is Empty", fill="#F8FAFC", anchor="lt", font=font_head)
            draw.text((120, 330), "Add YouTube videos or photos to start streaming!", fill="#94A3B8", anchor="lt", font=font_sub)

            # Web Request URL (大きく完全表記)
            draw.rectangle([(120, 420), (1200, 560)], fill="#1E293B", outline="#334155", width=2)
            draw.text((150, 450), "Web Request URL (手入力・ブラウザ用):", fill="#38BDF8", anchor="lt", font=font_info)
            draw.text((150, 495), url, fill="#FFFFFF", anchor="lt", font=font_url)

            draw.text((120, 610), "📱 Scan the QR code on the right with your smartphone", fill="#CBD5E1", anchor="lt", font=font_info)
            draw.text((120, 655), "🌐 Or enter the Web Request URL above in any browser", fill="#94A3B8", anchor="lt", font=font_info)

            # 画面右下: QRコードカード (完全URL付き)
            try:
                qr = qrcode.QRCode(
                    version=1,
                    error_correction=qrcode.constants.ERROR_CORRECT_M,
                    box_size=7,
                    border=2,
                )
                qr.add_data(url)
                qr.make(fit=True)
                qr_img = qr.make_image(fill_color="#0F172A", back_color="#FFFFFF").convert("RGB")
                
                qr_w, qr_h = qr_img.size
                card_w = qr_w + 32
                card_h = qr_h + 80
                card_x = width - card_w - 90
                card_y = (height - card_h) // 2 + 30

                # 白角丸カード
                draw.rounded_rectangle(
                    [(card_x, card_y), (card_x + card_w, card_y + card_h)],
                    radius=14,
                    fill="#FFFFFF",
                    outline="#E2E8F0",
                    width=2
                )
                img.paste(qr_img, (card_x + 16, card_y + 16))

                draw.text((card_x + card_w // 2, card_y + qr_h + 30), "Scan to Request", fill="#64748B", anchor="mm", font=font_card_url)
                draw.text((card_x + card_w // 2, card_y + qr_h + 55), "スマホでスキャン", fill="#0F172A", anchor="mm", font=font_card_url)
            except Exception as e:
                log_print(f"[Core] Error generating compact QR code on standby: {e}")

        draw.text(
            (width // 2, height - 35),
            "🔄 映像が止まった・遅れた時は [Resync] を押してください / If lagging or frozen, please press Resync.",
            fill="#94A3B8",
            anchor="mm",
            font=font_footer
        )

        if notice_text:
            img = self._draw_notice_banner(img, notice_text)

        try:
            img.save(STANDBY_IMAGE_PATH, "PNG")
        except Exception as e:
            log_print(f"[Core] Failed to save standby image: {e}")

    def play_standby_loop(self, empty_slideshow=False):
        """キューが空、またはスライドショー写真未登録時に待機画面（QRコード・URL付き静止画）をHLS配信"""
        last_tunnel_url = self.tunnel_raw_url
        notice_text = "📷 スライドショー写真が未登録です（Webリモコンから写真をアップロードできます）" if empty_slideshow else None

        while self.is_running and not self.skip_event.is_set():
            if empty_slideshow:
                if self.get_playback_mode() != "slideshow":
                    break
                with self.photo_lock:
                    if len(self.photo_pool) > 0:
                        break
                self.status = "offline"
                self.status_detail = "Slideshow (No Photos — Standby Notice)"
            else:
                if self.get_playback_mode() == "slideshow":
                    break
                with self.queue_lock:
                    if len(self.play_queue) > 0:
                        break
                self.status = "offline"
                self.status_detail = "Standby (Waiting for Videos)"

            # 待機画像を生成（最新のトンネルURLと案内テキストを反映）
            self.generate_standby_image(notice_text=notice_text)
            if not os.path.exists(STANDBY_IMAGE_PATH):
                time.sleep(0.5)
                continue

            if not self.ensure_hls_receiver():
                time.sleep(1)
                continue

            clock_video = bool(self.config.get("overlay_clock_enabled", False) or self.config.get("overlay_clock_video", False))
            has_clock = bool(clock_video)
            clock_filter = get_clock_filter_for_config(self.config) if has_clock else None

            cmd = [
                get_ffmpeg_cmd(), "-re",
            ]
            if self.accumulated_pts > 0:
                cmd.extend(["-output_ts_offset", f"{self.accumulated_pts:.3f}"])
            cmd.extend([
                "-loop", "1", "-i", os.path.abspath(STANDBY_IMAGE_PATH),
                "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
            ])
            if has_clock and clock_filter:
                cmd.extend(["-vf", clock_filter])
            cmd.extend([
                "-c:v", "libx264",
                "-preset", "ultrafast",
                "-tune", "zerolatency",
                "-profile:v", "baseline",
                "-level", "3.1",
                "-bf", "0",
                "-g", "30",
                "-keyint_min", "30",
                "-sc_threshold", "0",
                "-pix_fmt", "yuv420p",
                "-r", "30",
                "-b:v", "1500k",
                "-maxrate", "1500k",
                "-bufsize", "1000k",
                "-c:a", "aac", "-b:a", "64k",
                "-fflags", "+nobuffer+flush_packets",
                "-flush_packets", "1",
                "-muxdelay", "0",
                "-muxpreload", "0",
                "-f", "mpegts", "pipe:1"
            ])

            try:
                proc = subprocess.Popen(
                    cmd, stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL, bufsize=0,
                    creationflags=CREATE_NO_WINDOW
                )
            except Exception as e:
                log_print(f"[Player] Error starting Standby sender: {e}")
                time.sleep(1)
                continue

            with self.process_lock:
                self.send_proc = proc

            stop_event = threading.Event()
            threading.Thread(target=self.relay_stream_data,
                             args=(proc, self.current_stdin, stop_event, False), daemon=True).start()
            threading.Thread(target=self.watch_send_proc,
                             args=(proc, stop_event), daemon=True).start()

            url_updated = False
            while self.is_running and not self.skip_event.is_set():
                if self.reload_stream_event.is_set():
                    self.reload_stream_event.clear()
                    break

                if empty_slideshow:
                    if self.get_playback_mode() != "slideshow":
                        break
                    with self.photo_lock:
                        if len(self.photo_pool) > 0:
                            break
                else:
                    if self.get_playback_mode() == "slideshow":
                        break
                    with self.queue_lock:
                        if len(self.play_queue) > 0:
                            break

                if self.tunnel_raw_url != last_tunnel_url:
                    last_tunnel_url = self.tunnel_raw_url
                    url_updated = True
                    log_print(f"[Player] Tunnel URL updated ({last_tunnel_url}). Refreshing standby stream with public QR...")
                    break

                time.sleep(0.5)

            stop_event.set()
            with self.process_lock:
                if self.send_proc:
                    kill_proc(self.send_proc)
                self.send_proc = None

            self.accumulated_pts += self.last_stream_duration + 0.1
            log_print(f"[Player] Standby exited. Updated accumulated_pts: {self.accumulated_pts:.2f}s")

            if url_updated:
                time.sleep(0.3)
                continue
            else:
                break

    def queue_monitor_loop(self):
        log_print("[Monitor] Queue monitor started.")
        while self.is_running:
            try:
                current_mode = self.get_playback_mode()

                # ==================== モード1: 写真スライドショー ====================
                if current_mode == "slideshow":
                    photos = self.get_photos()
                    if not photos:
                        self.current_video = None
                        self.play_standby_loop(empty_slideshow=True)
                        time.sleep(0.3)
                        continue

                    # 写真を順番（またはシャッフル）に取得
                    with self.photo_lock:
                        if self.config.get("shuffle", False):
                            next_photo = random.choice(self.photo_pool)
                        else:
                            self.slideshow_index %= len(self.photo_pool)
                            next_photo = self.photo_pool[self.slideshow_index]
                            self.slideshow_index = (self.slideshow_index + 1) % len(self.photo_pool)

                    log_print(f"[Monitor] Showing Photo in slideshow: {next_photo.get('title')}")
                    self.current_video = next_photo
                    self.skip_event.clear()
                    self.video_done_event.clear()
                    self.status = "streaming"
                    self.status_detail = f"Showing Photo: {next_photo.get('title')}"

                    stop_event = self.play_image(next_photo)
                    if stop_event is None:
                        log_print("[Monitor] Failed to display photo. Skipping to next.")
                        self.status = "error"
                        self.status_detail = "Failed to load photo"
                        time.sleep(1)
                        continue

                    elapsed = 0.0
                    duration_for_log = float(self.config.get("image_display_duration", 15))
                    while self.is_running and not self.skip_event.is_set():
                        # モード切替検知
                        if self.get_playback_mode() != "slideshow":
                            break

                        # 設定変更・写真更新ホットリロード要求
                        if self.reload_stream_event.is_set():
                            self.reload_stream_event.clear()
                            log_print("[Monitor] Hot-reloading slideshow photo stream...")
                            stop_event.set()
                            with self.process_lock:
                                if self.send_proc:
                                    kill_proc(self.send_proc)
                                self.send_proc = None
                            time.sleep(0.2)
                            break

                        auto_advance = bool(self.config.get("image_auto_advance", True))
                        if not self.image_paused and auto_advance:
                            elapsed += 0.2
                            duration = float(self.config.get("image_display_duration", 15))
                            if elapsed >= duration:
                                log_print(f"[Monitor] Photo display time elapsed ({duration}s).")
                                break

                        time.sleep(0.2)
                        with self.process_lock:
                            proc = self.send_proc
                            h_proc = self.hls_proc
                        if proc and proc.poll() is not None:
                            if elapsed < duration_for_log:
                                log_print(
                                    f"[Monitor] WARNING: Photo sender exited after {elapsed:.1f}s "
                                    f"(expected {duration_for_log}s, exit={proc.returncode}). "
                                    f"Photo: {next_photo.get('title')}"
                                )
                            break
                        if h_proc and h_proc.poll() is not None:
                            log_print("[Monitor] Receiver FFmpeg crashed or exited during photo.")
                            self.status = "error"
                            self.status_detail = "Offline (Receiver Error)"
                            break

                    stop_event.set()
                    with self.process_lock:
                        proc = self.send_proc
                        if proc:
                            kill_proc(proc)
                        self.send_proc = None

                    self.accumulated_pts += self.last_stream_duration + 0.1
                    log_print(f"[Monitor] Photo finished. Updated accumulated_pts: {self.accumulated_pts:.2f}s")

                    if self.skip_event.is_set():
                        log_print("[Monitor] Photo skipped.")
                        self.skip_event.clear()
                    self.video_done_event.clear()
                    time.sleep(0.1)
                    continue

                # ==================== モード2 & 3: 通常動画 / ラジオBGM ====================
                next_item = None
                with self.queue_lock:
                    if self.play_queue:
                        if self.config.get("shuffle", False):
                            idx = random.randrange(len(self.play_queue))
                            next_item = self.play_queue.pop(idx)
                        else:
                            next_item = self.play_queue.pop(0)

                if not next_item:
                    self.current_video = None
                    self.status = "offline"
                    self.status_detail = "Standby (Waiting for Videos)"
                    self.play_standby_loop(empty_slideshow=False)
                    time.sleep(0.3)
                    continue

                # 履歴に追加 (最大20件)
                with self.queue_lock:
                    self.history_stack.append(next_item)
                    if len(self.history_stack) > 20:
                        self.history_stack.pop(0)

                is_radio = (current_mode == "radio")
                log_print(f"[Monitor] Loading: {next_item.get('title')} (is_radio: {is_radio})")
                self.current_video = next_item
                self.skip_event.clear()
                self.video_done_event.clear()

                self.status = "buffering"
                self.status_detail = f"Loading {'[Radio]' if is_radio else ''}: {next_item.get('title')}..."

                if is_radio:
                    stop_event = self.play_radio(next_item)
                else:
                    stop_event = self.play_video(next_item)

                if stop_event is None:
                    log_print("[Monitor] Failed to play. Skipping to next.")
                    self.status = "error"
                    self.status_detail = "Failed to load stream"
                    time.sleep(1)
                    continue

                self.status = "streaming"
                self.status_detail = "Active (Radio BGM)" if is_radio else "Active (Streaming)"

                # 次の曲のバックグラウンド先読み（プリフェッチ）を開始
                with self.queue_lock:
                    next_queued = self.play_queue[0] if self.play_queue else None
                if next_queued:
                    threading.Thread(target=self.prefetch_item, args=(next_queued,), daemon=True).start()

                # 終了 or スキップを待つ (ホットリロード対応)
                while self.is_running and not self.skip_event.is_set():
                    # 再生モードがスライドショーへ切り替わった場合
                    if self.get_playback_mode() == "slideshow":
                        log_print("[Monitor] Switched to slideshow mode during video playback. Transitioning...")
                        break

                    # 設定変更による即時ホットリロード要求
                    if self.reload_stream_event.is_set():
                        self.reload_stream_event.clear()
                        seek = max(0, time.time() - (self.current_video_start_time or time.time()))
                        is_radio_now = (self.get_playback_mode() == "radio")
                        log_print(f"[Monitor] Hot-reloading active stream (radio={is_radio_now}) with updated settings at seek={int(seek)}s...")
                        stop_event.set()
                        with self.process_lock:
                            if self.send_proc:
                                kill_proc(self.send_proc)
                            self.send_proc = None
                        time.sleep(0.1)
                        if is_radio_now:
                            stop_event = self.play_radio(next_item, seek_seconds=seek)
                        else:
                            stop_event = self.play_video(next_item, seek_seconds=seek)
                        if stop_event is None:
                            break

                    with self.process_lock:
                        h_proc = self.hls_proc
                    if h_proc and h_proc.poll() is not None:
                        log_print("[Monitor] Receiver FFmpeg crashed or exited.")
                        self.status = "error"
                        self.status_detail = "Offline (Receiver Error)"
                        break

                    item_dur = float(next_item.get("duration") or 0)
                    elapsed_play = (time.time() - self.current_video_start_time) if self.current_video_start_time else 0

                    # 送信側がデータ送信完了（先読み完了）した場合
                    if self.video_done_event.is_set():
                        if item_dur > 0:
                            if elapsed_play >= item_dur:
                                log_print(f"[Monitor] Video playback finished naturally ({int(elapsed_play)}s / {int(item_dur)}s).")
                                break
                        else:
                            # duration不明の場合は即座に完了
                            break

                    # 曲の長さを大幅に超過した際のタイムアウト・フェイルセーフ
                    if item_dur > 0 and elapsed_play > item_dur + 10:
                        log_print(f"[Monitor] Video reached duration limit ({int(elapsed_play)}s / {int(item_dur)}s). Finishing.")
                        break

                    self.video_done_event.wait(timeout=0.3)

                # 自然終了（スキップではない）の場合、最後のバッファをプレイヤーが再生しきるまで設定秒数待機
                wait_secs = self.config.get("video_transition_wait_seconds", 1)
                if not self.skip_event.is_set() and self.is_running and wait_secs > 0:
                    log_print(f"[Monitor] Waiting {wait_secs} seconds for player buffer completion...")
                    self.status = "finishing"
                    self.status_detail = "Finishing Video..."
                    self.skip_event.wait(timeout=wait_secs)

                stop_event.set()
                with self.process_lock:
                    proc = self.send_proc
                    if proc:
                        kill_proc(proc)
                    self.send_proc = None

                # 動画再生時間を累積PTSに加算
                self.accumulated_pts += self.last_stream_duration + 0.1
                log_print(f"[Monitor] Video finished. Updated accumulated_pts: {self.accumulated_pts:.2f}s")

                # ループ再生が有効な場合、終了した動画をキューの末尾に再追加
                if self.config.get("loop_queue", False) and next_item:
                    with self.queue_lock:
                        self.play_queue.append(next_item)
                    log_print(f"[Monitor] Loop queue: re-added '{next_item.get('title')}' to end of queue.")

                if self.skip_event.is_set():
                    log_print("[Monitor] Video skipped.")
                    self.skip_event.clear()
                self.video_done_event.clear()

            except Exception as e:
                log_print(f"[Monitor] Exception in queue loop: {e}")
                self.status = "error"
                self.status_detail = "Offline (Monitor Error)"
                time.sleep(1)

    def start_tunnel(self):
        if not getattr(self, "enable_tunnel", True):
            port = self.config.get("port", 8000)
            self.tunnel_raw_url = f"http://localhost:{port}"
            self.tunnel_url = f"http://localhost:{port}/stream.m3u8"
            log_print(f"[Tunnel] Tunnel is DISABLED. Using local URL: {self.tunnel_url}")
            return None

        log_print("Starting Cloudflare Quick Tunnel...")
        if not os.path.exists(CLOUDFLARED_EXE):
            log_print(f"Error: cloudflared.exe not found at {CLOUDFLARED_EXE}")
            self.tunnel_url = "cloudflared.exe missing!"
            self.tunnel_raw_url = ""
            return None

        port = self.config.get("port", 8000)
        cmd = [os.path.abspath(CLOUDFLARED_EXE), "tunnel", "--url", f"http://localhost:{port}"]
        try:
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, encoding="utf-8", errors="replace",
                creationflags=CREATE_NO_WINDOW
            )
            with self.process_lock:
                self.tunnel_proc = proc
        except Exception as e:
            log_print(f"Error executing cloudflared: {e}")
            self.tunnel_url = "Launch error!"
            self.tunnel_raw_url = ""
            return None

        def read_tunnel_output():
            established = False
            while self.is_running:
                line = proc.stderr.readline()
                if not line:
                    break
                m = re.search(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com", line)
                if m:
                    self.tunnel_raw_url = m.group(0)
                    self.tunnel_url = self.tunnel_raw_url + "/stream.m3u8"
                    log_print(f"Cloudflare Tunnel Established: {self.tunnel_url}")
                    established = True
                    
            if not established and self.is_running:
                self.tunnel_url = "Tunnel failed to connect."

        threading.Thread(target=read_tunnel_output, daemon=True).start()
        return proc

    def start_background_tasks(self):
        """トンネル、常駐HLS受信プロセス、およびキュー監視のバックグラウンド開始"""
        self.ensure_hls_receiver()
        self.start_tunnel()
        t = threading.Thread(target=self.queue_monitor_loop, daemon=True)
        t.start()

    def shutdown(self):
        log_print("[Core] Shutting down StreamerCore...")
        self.is_running = False
        with self.process_lock:
            if self.current_stdin:
                try:
                    self.current_stdin.close()
                except Exception:
                    pass
                self.current_stdin = None
            kill_proc(self.send_proc)
            kill_proc(self.hls_proc)
            kill_proc(self.tunnel_proc)
            self.send_proc = None
            self.hls_proc = None
            self.tunnel_proc = None
        
        # プロセス終了・ファイルロック解除を確実に待ってから HLS ディレクトリ内を完全消去
        time.sleep(0.5)
        self.clean_hls_dir(all_files=True, preserve_images=False)
        log_print("[Core] HLS output directory completely cleaned.")
        log_print("[Core] Shutdown complete.")
