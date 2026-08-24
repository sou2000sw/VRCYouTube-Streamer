import os
import sys
import time
import re
import io
import json
import random
import socket
import threading
import subprocess
import urllib.request
import urllib.parse
import yt_dlp
import qrcode
from PIL import Image, ImageDraw, ImageFont, ImageOps

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
STANDBY_IMAGE_PATH = os.path.join(HLS_DIR, "standby.png")
QR_OVERLAY_PATH = os.path.join(HLS_DIR, "qr_overlay.png")
CLOUDFLARED_EXE = os.path.join(BASE_PATH, "cloudflared.exe")
LOCAL_FFMPEG = os.path.join(APP_DIR, "ffmpeg.exe")

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
    "hls_list_size": 10,
    "video_transition_wait_seconds": 5,
    "live_sync_duration_count": 4,
    "loop_queue": False,
    "shuffle": False,
    "allow_web_queue_add": True,
    "allow_web_queue_edit": True,
    "allow_web_playback_control": True,
    "image_display_duration": 15,
    "image_auto_advance": True,
    "overlay_qr_enabled": False,
    "overlay_qr_video": False,
    "overlay_qr_image": False,
    "overlay_qr_mode": "bottom-right",
    "radio_mode": False,
    "radio_bg_source": "standby"
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

def kill_proc(proc):
    if not proc:
        return
    try:
        proc.kill()
    except Exception:
        pass

MAX_PLAYLIST_ITEMS = 50
MAX_QUEUE_CAPACITY = 200

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

class StreamerCore:
    def __init__(self, override_port=None, override_host=None, override_enable_tunnel=None):
        self.config = DEFAULT_CONFIG.copy()
        self.load_config()
        if override_port is not None:
            self.config["port"] = override_port
        if override_host is not None:
            self.config["host"] = override_host
        if override_enable_tunnel is not None:
            self.config["enable_tunnel"] = bool(override_enable_tunnel)

        self.enable_tunnel = bool(self.config.get("enable_tunnel", True))

        os.makedirs(HLS_DIR, exist_ok=True)
        self.clean_hls_dir()

        # プロセスと同期
        self.hls_proc = None
        self.send_proc = None
        self.tunnel_proc = None
        self.current_stdin = None

        self.play_queue = [] # list of dict: [{"title": "...", "url": "...", "duration": ..., "type": "video"|"image"}]
        self.history_stack = [] # 履歴管理用 (最大20件)
        self.queue_lock = threading.Lock()
        self.process_lock = threading.Lock()

        # 状態
        # status: "offline", "buffering", "streaming", "finishing", "error"
        self.status = "offline"
        self.status_detail = "Offline (Queue Empty)"
        self.current_video = None # {"title": "...", "url": "...", "duration": ..., "type": ...}
        self.tunnel_url = "" # "https://xxx.trycloudflare.com/stream.m3u8"
        self.tunnel_raw_url = "" # "https://xxx.trycloudflare.com"
        self.is_running = True
        self.image_paused = not bool(self.config.get("image_auto_advance", True)) # 写真スライドショー一時停止フラグ

        self.skip_event = threading.Event()
        self.video_done_event = threading.Event()
        self.reload_stream_event = threading.Event()
        self.current_video_start_time = None

    def clean_hls_dir(self):
        try:
            for f in os.listdir(HLS_DIR):
                if f.endswith(".ts") or f.endswith(".m3u8"):
                    try:
                        os.remove(os.path.join(HLS_DIR, f))
                    except Exception:
                        pass
        except Exception as e:
            log_print(f"[Core] Warning cleaning HLS dir: {e}")

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
        if new_config:
            self.config.update(new_config)
            if "enable_tunnel" in new_config:
                self.enable_tunnel = bool(new_config["enable_tunnel"])
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
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
            "image_auto_advance": bool(self.config.get("image_auto_advance", True)),
            "overlay_qr_enabled": bool(self.config.get("overlay_qr_enabled", False) or self.config.get("overlay_qr_video", False) or self.config.get("overlay_qr_image", False)),
            "overlay_qr_video": bool(self.config.get("overlay_qr_video", False)),
            "overlay_qr_image": bool(self.config.get("overlay_qr_image", False)),
            "overlay_qr_mode": str(self.config.get("overlay_qr_mode", "bottom-right")),
            "radio_mode": bool(self.config.get("radio_mode", False)),
            "radio_bg_source": str(self.config.get("radio_bg_source", "standby")),
            "has_prev": has_prev,
            "permissions": {
                "allow_web_queue_add": bool(self.config.get("allow_web_queue_add", True)),
                "allow_web_queue_edit": bool(self.config.get("allow_web_queue_edit", True)),
                "allow_web_playback_control": bool(self.config.get("allow_web_playback_control", True))
            }
        }

    def set_radio_mode(self, enabled: bool):
        self.config["radio_mode"] = bool(enabled)
        self.save_config()
        log_print(f"[Core] Radio mode set to: {self.config['radio_mode']}")
        return self.config["radio_mode"]

    def set_radio_bg_source(self, source: str):
        if source in ("standby", "slideshow"):
            self.config["radio_bg_source"] = source
            self.save_config()
            log_print(f"[Core] Radio background source set to: {source}")
        return self.config.get("radio_bg_source", "standby")

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
        curr_advance = bool(self.config.get("image_auto_advance", True)) and not self.image_paused
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
        list_size = str(self.config.get("hls_list_size", 10))

        cmd = [
            get_ffmpeg_cmd(), "-y",
            "-fflags", "+nobuffer+flush_packets",
            "-i", "pipe:0",
            "-c:v", "copy",
            "-c:a", "copy",
            "-flush_packets", "1",
            "-f", "hls",
            "-hls_time", seg_time,
            "-hls_list_size", list_size,
            "-hls_flags", "delete_segments+split_by_time",
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

    def relay_stream_data(self, proc_to_read, stdin_to_write, stop_event):
        try:
            while not stop_event.is_set() and self.is_running:
                # read1 があれば即座に利用可能なパケット（1TSパケットでも）を読み出して遅延を防ぐ
                if hasattr(proc_to_read.stdout, "read1"):
                    data = proc_to_read.stdout.read1(65536)
                else:
                    data = proc_to_read.stdout.read(8192)
                if not data:
                    break
                try:
                    stdin_to_write.write(data)
                    stdin_to_write.flush()
                except Exception:
                    break
        except Exception:
            pass
        finally:
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

    def expand_playlist(self, url):
        """URLから動画情報リスト [{"url": ..., "title": ..., "duration": ...}] を展開"""
        is_safe, reason = is_safe_url(url)
        if not is_safe:
            log_print(f"[Core] Rejected unsafe URL: {reason}")
            return []

        ydl_opts = {
            "extract_flat": True,
            "skip_download": True,
            "quiet": True,
            "playlistend": MAX_PLAYLIST_ITEMS
        }
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
        ydl_opts = {
            "format": "bestvideo[vcodec^=avc1]+bestaudio[acodec^=mp4a]/best[vcodec^=avc1]/best",
            "quiet": True,
            "extractor_args": {
                "youtube": {
                    "player_client": ["ios", "android", "tv"]
                }
            }
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(youtube_url, download=False)
            video_url = audio_url = None
            if "requested_formats" in info:
                for fmt in info["requested_formats"]:
                    if fmt.get("vcodec") != "none" and fmt.get("acodec") == "none":
                        video_url = fmt.get("url")
                    elif fmt.get("acodec") != "none" and fmt.get("vcodec") == "none":
                        audio_url = fmt.get("url")
            if not video_url or not audio_url:
                video_url = info.get("url")
                audio_url = None
            
            headers = info.get("http_headers", {})
            return video_url, audio_url, info.get("title", "Unknown"), info.get("duration", 0), headers

    def get_audio_only_stream_urls(self, youtube_url):
        ydl_opts = {
            "format": "bestaudio[acodec^=mp4a]/bestaudio/best",
            "quiet": True,
            "extractor_args": {
                "youtube": {
                    "player_client": ["ios", "android", "tv"]
                }
            }
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(youtube_url, download=False)
            audio_url = info.get("url")
            headers = info.get("http_headers", {})
            return audio_url, info.get("title", "Unknown"), info.get("duration", 0), headers

    def get_radio_background_path(self):
        """BGM/ラジオモード用の背景画像パスを取得（待機画面または写真）"""
        source = self.config.get("radio_bg_source", "standby")
        if source == "slideshow":
            # 1. 写真キューにある画像を探す
            with self.queue_lock:
                for item in self.play_queue:
                    if item.get("type") == "image" and item.get("path") and os.path.exists(item["path"]):
                        return item["path"]
            # 2. キャッシュされた写真画像を探す
            if os.path.exists(IMAGE_CACHE_DIR):
                cached = [os.path.join(IMAGE_CACHE_DIR, f) for f in os.listdir(IMAGE_CACHE_DIR) if f.endswith((".png", ".jpg", ".jpeg"))]
                if cached:
                    return random.choice(cached)

        # デフォルトは待機画面 (QR & URLカード付き)
        self.generate_standby_image()
        if os.path.exists(STANDBY_IMAGE_PATH):
            return STANDBY_IMAGE_PATH
        return None

    def play_radio(self, video_info, seek_seconds=0):
        """BGM/ラジオモード: YouTube音声ストリーム + 静止画/写真を合成し、極小帯域でHLS配信"""
        url = video_info["url"]
        try:
            audio_url, title, duration, headers = self.get_audio_only_stream_urls(url)
            if not audio_url:
                raise ValueError("No audio stream URL returned by yt-dlp")
            self.current_video = {
                "title": f"📻 {title}",
                "url": url,
                "duration": duration,
                "is_radio": True
            }
            self.current_video_start_time = time.time() - max(0, seek_seconds)
            log_print(f"[Radio] Now Playing (BGM Audio): {title} (seek: {int(seek_seconds)}s)")
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

        bg_path = self.get_radio_background_path()
        if not bg_path or not os.path.exists(bg_path):
            self.generate_standby_image()
            bg_path = STANDBY_IMAGE_PATH

        headers_str = ""
        if headers:
            headers_str = "".join(f"{k}: {v}\r\n" for k, v in headers.items())

        input_opts = [
            "-reconnect", "1",
            "-reconnect_streamed", "1",
            "-reconnect_delay_max", "2",
            "-reconnect_on_network_error", "1",
            "-reconnect_on_http_error", "4xx,5xx",
            "-rw_timeout", "10000000",
        ]
        if headers_str:
            input_opts.extend(["-headers", headers_str])
        if seek_seconds > 0:
            input_opts.extend(["-ss", str(int(seek_seconds))])

        cmd = [
            get_ffmpeg_cmd(), "-re",
            "-loop", "1", "-i", os.path.abspath(bg_path),
        ]
        cmd.extend(input_opts)
        cmd.extend(["-i", audio_url])
        cmd.extend([
            "-map", "0:v:0",
            "-map", "1:a:0",
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
        url = video_info["url"]
        try:
            video_url, audio_url, title, duration, headers = self.get_stream_urls(url)
            self.current_video = {
                "title": title,
                "url": url,
                "duration": duration
            }
            self.current_video_start_time = time.time() - max(0, seek_seconds)
            log_print(f"[Player] Now Playing: {title} (seek: {int(seek_seconds)}s)")
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

        input_opts = [
            "-reconnect", "1",
            "-reconnect_streamed", "1",
            "-reconnect_delay_max", "2",
            "-reconnect_on_network_error", "1",
            "-reconnect_on_http_error", "4xx,5xx",
            "-rw_timeout", "10000000",
        ]
        if headers_str:
            input_opts.extend(["-headers", headers_str])
        if seek_seconds > 0:
            input_opts.extend(["-ss", str(int(seek_seconds))])

        overlay_video = bool(self.config.get("overlay_qr_enabled", False) or self.config.get("overlay_qr_video", False))
        qr_overlay_file = self.generate_qr_overlay_image() if overlay_video else None

        cmd = [get_ffmpeg_cmd(), "-re", "-fflags", "+genpts"]
        cmd.extend(input_opts)
        cmd.extend(["-i", video_url])
        if audio_url:
            cmd.extend(input_opts)
            cmd.extend(["-i", audio_url])
        
        if overlay_video and qr_overlay_file and os.path.exists(qr_overlay_file):
            qr_idx = 2 if audio_url else 1
            cmd.extend(["-loop", "1", "-i", os.path.abspath(qr_overlay_file)])
            mode = self.config.get("overlay_qr_mode", "bottom-right")
            if mode == "fullscreen":
                # scale2refで動画解像度に合わせてオーバーレイ画像を自動スケーリング（見切れ防止）
                overlay_filter = f"[{qr_idx}:v][0:v]scale2ref[qr_scaled][vmain];[vmain][qr_scaled]overlay=0:0:shortest=1[vout]"
            else:
                overlay_filter = f"[0:v][{qr_idx}:v]overlay=main_w-overlay_w-25:main_h-overlay_h-25:shortest=1[vout]"

            cmd.extend([
                "-filter_complex", overlay_filter,
                "-map", "[vout]"
            ])
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
                "-f", "mpegts", "pipe:1"
            ])
        else:
            cmd.extend(["-map", "0:v:0"])
            if audio_url:
                cmd.extend(["-map", "1:a:0"])
            else:
                cmd.extend(["-map", "0:a:0?"])
            cmd.extend(["-c:v", "copy", "-c:a", "aac", "-b:a", "128k",
                        "-af", "aresample=async=1", "-f", "mpegts", "pipe:1"])

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

    def add_image_file(self, file_path, title=None):
        """ローカル画像ファイルを最適化してキューに追加"""
        with self.queue_lock:
            if len(self.play_queue) >= MAX_QUEUE_CAPACITY:
                log_print(f"[Core] Queue capacity reached ({MAX_QUEUE_CAPACITY}).")
                return None

        cached_path = self.optimize_image_to_cache(file_path)
        if not cached_path:
            return None

        if not title:
            title = os.path.splitext(os.path.basename(file_path))[0]

        duration = int(self.config.get("image_display_duration", 15))
        item = {
            "type": "image",
            "title": f"🖼 {title}",
            "url": os.path.basename(file_path),
            "path": cached_path,
            "duration": duration
        }
        with self.queue_lock:
            self.play_queue.append(item)
        log_print(f"[Core] Added photo to queue: {title} ({duration}s)")
        return item

    def add_image_bytes(self, image_bytes, original_filename="photo.jpg"):
        """アップロードされた画像バイナリを最適化してキューに追加"""
        with self.queue_lock:
            if len(self.play_queue) >= MAX_QUEUE_CAPACITY:
                log_print(f"[Core] Queue capacity reached ({MAX_QUEUE_CAPACITY}).")
                return None

        cached_path = self.optimize_image_to_cache(image_bytes)
        if not cached_path:
            return None

        title = os.path.splitext(os.path.basename(original_filename))[0] or "Uploaded Photo"
        duration = int(self.config.get("image_display_duration", 15))
        item = {
            "type": "image",
            "title": f"🖼 {title}",
            "url": original_filename,
            "path": cached_path,
            "duration": duration
        }
        with self.queue_lock:
            self.play_queue.append(item)
        log_print(f"[Core] Added uploaded photo to queue: {title} ({duration}s)")
        return item

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

        cmd = [
            get_ffmpeg_cmd(), "-re",
            "-loop", "1", "-i", os.path.abspath(playback_image_path),
            "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
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
        ]

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
                         args=(proc, self.current_stdin, stop_event), daemon=True).start()
        threading.Thread(target=self.watch_send_proc,
                         args=(proc, stop_event), daemon=True).start()
        return stop_event

    def add_to_queue(self, url):
        """URL（動画または画像）を解析してキューに追加"""
        with self.queue_lock:
            if len(self.play_queue) >= MAX_QUEUE_CAPACITY:
                log_print(f"[Core] Cannot add items: Queue reached max capacity ({MAX_QUEUE_CAPACITY}).")
                return []

        # 画像URLの場合
        if is_image_url_or_file(url):
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
            self.play_queue.clear()
        log_print("[Core] Queue cleared.")

    def delete_queue_item(self, idx):
        with self.queue_lock:
            if 0 <= idx < len(self.play_queue):
                removed = self.play_queue.pop(idx)
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

                draw.text((width // 2, 45), "VRCYouTube Live Streamer", fill=(56, 189, 248, 255), anchor="mm", font=font_title)
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

    def get_image_for_playback(self, image_path):
        """写真再生時、overlay_qr_enabled設定に応じてQRコード・URLを合成した画像パスを返す"""
        overlay_enabled = bool(self.config.get("overlay_qr_enabled", False) or self.config.get("overlay_qr_image", False))
        if not overlay_enabled:
            return image_path

        qr_path = self.generate_qr_overlay_image()
        if not qr_path or not os.path.exists(qr_path):
            return image_path

        try:
            base_img = Image.open(image_path).convert("RGBA")
            qr_img = Image.open(qr_path).convert("RGBA")

            bw, bh = base_img.size
            qw, qh = qr_img.size
            mode = self.config.get("overlay_qr_mode", "bottom-right")

            if mode == "fullscreen":
                base_img.alpha_composite(qr_img, dest=(0, 0))
            else:
                pos_x = bw - qw - 25
                pos_y = bh - qh - 25
                base_img.alpha_composite(qr_img, dest=(pos_x, pos_y))

            temp_path = os.path.join(IMAGE_CACHE_DIR, f"playback_overlay_{int(time.time())}.png")
            base_img.convert("RGB").save(temp_path, "PNG")
            return temp_path
        except Exception as e:
            log_print(f"[Core] Failed to composite QR overlay onto image: {e}")
            return image_path

    def generate_standby_image(self):
        """待機用画面（QRコード & URL付き 1920x1080）を生成して保存"""
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

        try:
            font_title = ImageFont.truetype("arial.ttf", 52)
            font_head = ImageFont.truetype("arial.ttf", 44)
            font_sub = ImageFont.truetype("arial.ttf", 30)
            font_url = ImageFont.truetype("arial.ttf", 34)
            font_info = ImageFont.truetype("arial.ttf", 24)
            font_card_url = ImageFont.truetype("arial.ttf", 16)
        except Exception:
            font_title = font_head = font_sub = font_url = font_info = font_card_url = ImageFont.load_default()

        draw.text((width // 2, 45), "VRCYouTube Live Streamer", fill="#38BDF8", anchor="mm", font=font_title)

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

        draw.text((width // 2, height - 35), "VRChat YouTube Streamer • Powered by yt-dlp & FFmpeg", fill="#475569", anchor="mm", font=font_info)

        try:
            img.save(STANDBY_IMAGE_PATH, "PNG")
        except Exception as e:
            log_print(f"[Core] Failed to save standby image: {e}")

    def play_standby_loop(self):
        """キューが空のときに待機画面（QRコード・URL付き静止画）をHLS配信"""
        last_tunnel_url = self.tunnel_raw_url

        while self.is_running and not self.skip_event.is_set():
            with self.queue_lock:
                if len(self.play_queue) > 0:
                    break

            # 待機画像を生成（最新のトンネルURLを反映）
            self.generate_standby_image()
            if not os.path.exists(STANDBY_IMAGE_PATH):
                time.sleep(0.5)
                continue

            if not self.ensure_hls_receiver():
                time.sleep(1)
                continue

            cmd = [
                get_ffmpeg_cmd(), "-re",
                "-loop", "1", "-i", os.path.abspath(STANDBY_IMAGE_PATH),
                "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
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
            ]

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
                             args=(proc, self.current_stdin, stop_event), daemon=True).start()
            threading.Thread(target=self.watch_send_proc,
                             args=(proc, stop_event), daemon=True).start()

            # キューに動画が入るか、またはトンネルURLが更新されるまでループ
            url_updated = False
            while self.is_running and not self.skip_event.is_set():
                with self.queue_lock:
                    if len(self.play_queue) > 0:
                        break

                # トンネルURLが後から確定・変化した場合、新しいQRコードで待機ストリームを再起動
                if self.tunnel_raw_url != last_tunnel_url:
                    last_tunnel_url = self.tunnel_raw_url
                    url_updated = True
                    log_print(f"[Player] Tunnel URL updated ({last_tunnel_url}). Refreshing standby stream with public QR...")
                    break

                time.sleep(0.5)

            # 送信プロセスを停止
            stop_event.set()
            with self.process_lock:
                if self.send_proc:
                    kill_proc(self.send_proc)
                self.send_proc = None

            # トンネルURL更新による再起動の場合は、キューが空のまま再度ループして新しい画像で配信開始
            if url_updated:
                time.sleep(0.3)
                continue
            else:
                break

    def queue_monitor_loop(self):
        log_print("[Monitor] Queue monitor started.")
        while self.is_running:
            try:
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
                    # 待機画面（QRコード & URL）を配信しながら待機
                    self.play_standby_loop()
                    time.sleep(0.5)
                    continue

                # 履歴に追加 (最大20件)
                with self.queue_lock:
                    self.history_stack.append(next_item)
                    if len(self.history_stack) > 20:
                        self.history_stack.pop(0)

                is_img = (next_item.get("type") == "image")
                log_print(f"[Monitor] Loading: {next_item.get('title')} (is_image: {is_img})")
                self.current_video = next_item
                self.skip_event.clear()
                self.video_done_event.clear()

                if is_img:
                    self.status = "streaming"
                    self.status_detail = f"Showing Photo: {next_item.get('title')}"
                    stop_event = self.play_image(next_item)
                    if stop_event is None:
                        log_print("[Monitor] Failed to display photo. Skipping to next.")
                        self.status = "error"
                        self.status_detail = "Failed to load photo"
                        time.sleep(1)
                        continue

                    # 写真スライドショーのタイマー監視（一時停止対応 & ホットリロード対応）
                    elapsed = 0.0
                    while self.is_running and not self.skip_event.is_set():
                        # 設定変更による即時ホットリロード要求
                        if self.reload_stream_event.is_set():
                            self.reload_stream_event.clear()
                            log_print("[Monitor] Hot-reloading active photo stream with updated QR settings...")
                            stop_event.set()
                            with self.process_lock:
                                if self.send_proc:
                                    kill_proc(self.send_proc)
                                self.send_proc = None
                            time.sleep(0.1)
                            stop_event = self.play_image(next_item)
                            if stop_event is None:
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

                    if self.config.get("loop_queue", False) and next_item:
                        with self.queue_lock:
                            self.play_queue.append(next_item)
                        log_print(f"[Monitor] Loop queue: re-added photo '{next_item.get('title')}' to end of queue.")

                    if self.skip_event.is_set():
                        log_print("[Monitor] Photo skipped.")
                        self.skip_event.clear()
                    self.video_done_event.clear()
                    time.sleep(0.3)
                    continue

                # 動画 / BGM・ラジオ再生フロー
                is_radio = bool(self.config.get("radio_mode", False))
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
                    time.sleep(2)
                    continue

                self.status = "streaming"
                self.status_detail = "Active (Radio BGM)" if is_radio else "Active (Streaming)"

                # 終了 or スキップを待つ (ホットリロード対応)
                while self.is_running and not self.skip_event.is_set():
                    # 設定変更による即時ホットリロード要求
                    if self.reload_stream_event.is_set():
                        self.reload_stream_event.clear()
                        seek = max(0, time.time() - (self.current_video_start_time or time.time()))
                        is_radio_now = bool(self.config.get("radio_mode", False))
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

                    if self.video_done_event.wait(timeout=0.4):
                        break
                    with self.process_lock:
                        proc = self.send_proc
                        h_proc = self.hls_proc
                    if proc and proc.poll() is not None:
                        break
                    if h_proc and h_proc.poll() is not None:
                        log_print("[Monitor] Receiver FFmpeg crashed or exited.")
                        self.status = "error"
                        self.status_detail = "Offline (Receiver Error)"
                        break

                # 自然終了（スキップではない）の場合、最後のバッファをプレイヤーが再生しきるまで設定秒数待機
                wait_secs = self.config.get("video_transition_wait_seconds", 5)
                if not self.skip_event.is_set() and self.is_running:
                    log_print(f"[Monitor] Waiting {wait_secs} seconds for player buffer completion...")
                    self.status = "finishing"
                    self.status_detail = "Finishing Video..."
                    time.sleep(wait_secs)

                stop_event.set()
                with self.process_lock:
                    proc = self.send_proc
                    if proc:
                        kill_proc(proc)
                    self.send_proc = None

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
        log_print("[Core] Shutdown complete.")
