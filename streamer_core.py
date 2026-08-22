import os
import sys
import time
import re
import json
import random
import threading
import subprocess
import yt_dlp
import qrcode
from PIL import Image, ImageDraw, ImageFont

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
STANDBY_IMAGE_PATH = os.path.join(HLS_DIR, "standby.png")
CLOUDFLARED_EXE = os.path.join(BASE_PATH, "cloudflared.exe")
LOCAL_FFMPEG = os.path.join(APP_DIR, "ffmpeg.exe")

DEFAULT_CONFIG = {
    "host": "127.0.0.1",
    "port": 8000,
    "hls_segment_time": 3,
    "hls_list_size": 10,
    "video_transition_wait_seconds": 5,
    "live_sync_duration_count": 4,
    "loop_queue": False,
    "shuffle": False,
    "allow_web_queue_add": True,
    "allow_web_queue_edit": True,
    "allow_web_playback_control": True
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

class StreamerCore:
    def __init__(self, override_port=None, override_host=None):
        self.config = DEFAULT_CONFIG.copy()
        self.load_config()
        if override_port is not None:
            self.config["port"] = override_port
        if override_host is not None:
            self.config["host"] = override_host

        os.makedirs(HLS_DIR, exist_ok=True)
        self.clean_hls_dir()

        # プロセスと同期
        self.hls_proc = None
        self.send_proc = None
        self.tunnel_proc = None
        self.current_stdin = None

        self.play_queue = [] # list of dict: [{"title": "...", "url": "...", "duration": ...}]
        self.queue_lock = threading.Lock()
        self.process_lock = threading.Lock()

        # 状態
        # status: "offline", "buffering", "streaming", "finishing", "error"
        self.status = "offline"
        self.status_detail = "Offline (Queue Empty)"
        self.current_video = None # {"title": "...", "url": "...", "duration": ...}
        self.tunnel_url = "" # "https://xxx.trycloudflare.com/stream.m3u8"
        self.tunnel_raw_url = "" # "https://xxx.trycloudflare.com"
        self.is_running = True

        self.skip_event = threading.Event()
        self.video_done_event = threading.Event()

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
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
            log_print(f"[Core] Saved config to {CONFIG_FILE}")
            return True
        except Exception as e:
            log_print(f"[Core] Failed to save config: {e}")
            return False

    def get_status_data(self):
        with self.queue_lock:
            queue_copy = [dict(item) for item in self.play_queue]

        stream_url = f"{self.tunnel_raw_url}/stream.m3u8" if self.tunnel_raw_url else ""
        return {
            "status": self.status,
            "status_detail": self.status_detail,
            "tunnel_url": self.tunnel_raw_url,
            "stream_url": stream_url,
            "current_video": self.current_video,
            "queue": queue_copy,
            "loop_queue": bool(self.config.get("loop_queue", False)),
            "shuffle": bool(self.config.get("shuffle", False)),
            "permissions": {
                "allow_web_queue_add": bool(self.config.get("allow_web_queue_add", True)),
                "allow_web_queue_edit": bool(self.config.get("allow_web_queue_edit", True)),
                "allow_web_playback_control": bool(self.config.get("allow_web_playback_control", True))
            }
        }

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
            "-i", "pipe:0",
            "-c:v", "copy",
            "-c:a", "copy",
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
                data = proc_to_read.stdout.read(65536)
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

    def play_video(self, video_info):
        url = video_info["url"]
        try:
            video_url, audio_url, title, duration, headers = self.get_stream_urls(url)
            self.current_video = {
                "title": title,
                "url": url,
                "duration": duration
            }
            log_print(f"[Player] Now Playing: {title}")
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

        cmd = [get_ffmpeg_cmd(), "-re", "-fflags", "+genpts"]
        cmd.extend(input_opts)
        cmd.extend(["-i", video_url])
        if audio_url:
            cmd.extend(input_opts)
            cmd.extend(["-i", audio_url])
        
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

    def add_to_queue(self, url):
        """URL（単体またはプレイリスト）を解析してキューに追加"""
        with self.queue_lock:
            if len(self.play_queue) >= MAX_QUEUE_CAPACITY:
                log_print(f"[Core] Cannot add items: Queue reached max capacity ({MAX_QUEUE_CAPACITY}).")
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

    def generate_standby_image(self):
        """待機用画面（QRコード & URL付き 1920x1080）を生成して保存"""
        is_tunnel_ready = bool(self.tunnel_raw_url and "trycloudflare.com" in self.tunnel_raw_url)
        url = self.tunnel_raw_url if is_tunnel_ready else f"http://localhost:{self.config.get('port', 8000)}"

        width, height = 1920, 1080
        img = Image.new("RGB", (width, height), color="#0F172A") # Dark slate
        draw = ImageDraw.Draw(img)

        # 1. Background accents
        draw.rectangle([(0, 0), (width, 90)], fill="#1E293B")
        draw.rectangle([(0, height - 70), (width, height)], fill="#1E293B")

        # 2. Header text
        try:
            font_title = ImageFont.truetype("arial.ttf", 52)
            font_sub = ImageFont.truetype("arial.ttf", 30)
            font_url = ImageFont.truetype("arial.ttf", 34)
            font_info = ImageFont.truetype("arial.ttf", 24)
        except Exception:
            font_title = font_sub = font_url = font_info = ImageFont.load_default()

        draw.text((width // 2, 45), "VRCYouTube Live Streamer", fill="#38BDF8", anchor="mm", font=font_title)
        
        if is_tunnel_ready:
            draw.text((width // 2, 140), "Queue is Empty — Request a video from your smartphone or browser!", fill="#94A3B8", anchor="mm", font=font_sub)
        else:
            draw.text((width // 2, 140), "Connecting to Cloudflare Tunnel... Please wait a moment.", fill="#F59E0B", anchor="mm", font=font_sub)

        # 3. QR Code Generation
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
            
            # Place QR Code at Center
            qr_w, qr_h = qr_img.size
            qr_x = (width - qr_w) // 2
            qr_y = (height - qr_h) // 2 - 15

            # Draw border card around QR
            card_pad = 22
            draw.rectangle(
                [(qr_x - card_pad, qr_y - card_pad), (qr_x + qr_w + card_pad, qr_y + qr_h + card_pad)],
                fill="#FFFFFF"
            )
            img.paste(qr_img, (qr_x, qr_y))
        except Exception as e:
            log_print(f"[Core] Error generating QR code: {e}")
            qr_y = height // 2

        # 4. URL and Instructions under QR
        url_box_y = height - 160
        if is_tunnel_ready:
            draw.text((width // 2, url_box_y), f"Web Request URL: {url}", fill="#F8FAFC", anchor="mm", font=font_url)
            draw.text((width // 2, url_box_y + 45), "Scan this QR code with your phone or visit the URL to add YouTube videos to the queue.", fill="#64748B", anchor="mm", font=font_info)
        else:
            draw.text((width // 2, url_box_y), "Public URL will appear here once connected...", fill="#94A3B8", anchor="mm", font=font_url)
            draw.text((width // 2, url_box_y + 45), "Establishing secure tunnel to Cloudflare network.", fill="#64748B", anchor="mm", font=font_info)

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
                "-c:v", "libx264", "-preset", "ultrafast", "-tune", "stillimage", "-pix_fmt", "yuv420p",
                "-r", "25", "-g", "50",
                "-c:a", "aac", "-b:a", "64k",
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

                log_print(f"[Monitor] Loading: {next_item.get('title')}")
                self.current_video = next_item
                self.status = "buffering"
                self.status_detail = f"Loading: {next_item.get('title')}..."
                self.skip_event.clear()
                self.video_done_event.clear()

                stop_event = self.play_video(next_item)
                if stop_event is None:
                    log_print("[Monitor] Failed to play. Skipping to next.")
                    self.status = "error"
                    self.status_detail = "Failed to load stream"
                    time.sleep(2)
                    continue

                self.status = "streaming"
                self.status_detail = "Active (Streaming)"

                # 終了 or スキップを待つ
                while self.is_running:
                    if self.video_done_event.wait(timeout=0.5):
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
            kill_proc(self.send_proc)
            kill_proc(self.hls_proc)
            if self.tunnel_proc:
                try:
                    self.tunnel_proc.terminate()
                except Exception:
                    pass
        log_print("[Core] Shutdown complete.")
