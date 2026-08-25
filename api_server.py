import os
import sys
import re
import json
import http.server
import socketserver
import threading
import time
import ipaddress
from urllib.parse import urlparse
from streamer_core import BASE_PATH, HLS_DIR, StreamerCore, log_print

def _ui_html_candidates():
    """
    ui/index.html の探索候補を優先順で返す。

    1. EXE と同じフォルダ  … 利用者が UI を差し替えたい場合の上書き先
    2. スクリプトと同じ場所 … 開発時（リポジトリ直下の ui/）
    3. カレントディレクトリ
    4. BASE_PATH           … PyInstaller onefile に同梱された既定 UI (sys._MEIPASS)
    """
    roots = []
    if getattr(sys, "frozen", False):
        roots.append(os.path.dirname(os.path.abspath(sys.executable)))
    roots.append(os.path.dirname(os.path.abspath(__file__)))
    roots.append(os.getcwd())
    roots.append(BASE_PATH)

    candidates = []
    seen = set()
    for root in roots:
        if not root or root in seen:
            continue
        seen.add(root)
        candidates.append(os.path.join(root, "ui", "index.html"))
        candidates.append(os.path.join(root, "plugin", "ui", "index.html"))
    return candidates


def get_ui_html():
    """
    Web リモコン UI (ui/index.html) を読み込む。

    v2.6.0 以降、UI の正本は ui/index.html ただ一つ。api_server.py 側に UI を複製すると
    必ずどちらかが腐るため（実際 v2.6.0 の内蔵テンプレートは <body> ごと欠落して配信されていた）、
    内蔵の複製は持たない。正本が見つからない場合は「壊れた UI」ではなく、
    原因と復旧手順を示す診断ページを返す（fail-closed）。
    """
    for path in _ui_html_candidates():
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return f.read()
            except Exception as e:
                log_print(f"[APIServer] Failed to read UI asset {path}: {e}")
    log_print("[APIServer] UI asset 'ui/index.html' not found. Serving diagnostic page.")
    return UI_MISSING_TEMPLATE


UI_MISSING_TEMPLATE = """<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>VRCYouTube Streamer - UI アセット未検出</title>
<style>
  :root { color-scheme: dark; }
  body { margin:0; padding:2rem 1.25rem; background:#121214; color:#e4e4e7;
         font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Noto Sans JP",sans-serif;
         line-height:1.7; }
  main { max-width:44rem; margin:0 auto; }
  h1 { font-size:1.25rem; margin:0 0 .25rem; color:#f43f5e; }
  p  { color:#a1a1aa; font-size:.9rem; }
  ol { color:#a1a1aa; font-size:.9rem; padding-left:1.2rem; }
  code { background:#202024; border:1px solid #27272a; border-radius:.25rem;
         padding:.1rem .35rem; font-size:.85em; color:#38bdf8; }
  .card { background:#18181b; border:1px solid #27272a; border-radius:.6rem;
          padding:1rem 1.25rem; margin-top:1.25rem; }
  .url { display:block; margin-top:.4rem; word-break:break-all; color:#38bdf8;
         font-family:ui-monospace,SFMono-Regular,Consolas,monospace; font-size:.85rem; }
</style>
</head>
<body>
<main>
  <h1>Web リモコン UI を読み込めませんでした</h1>
  <p>UI の正本である <code>ui/index.html</code> が見つかりません。
     配信機能（HLS）自体は正常に稼働しています。</p>

  <div class="card">
    <strong>VRChat / プレイヤー用 ストリーム URL</strong>
    <span class="url">__TUNNEL_STREAM_URL__</span>
  </div>

  <div class="card">
    <strong>復旧手順</strong>
    <ol>
      <li><code>ui/index.html</code> を <code>VRCYouTubeStreamer.exe</code> と同じフォルダの
          <code>ui/</code> に配置する（フォルダごと）。</li>
      <li>ソースからビルドした場合は
          <code>python build_exe.py</code> で再ビルドする（UI は EXE に同梱されます）。</li>
      <li>それでも直らない場合は起動ログの
          <code>[APIServer] UI asset ... not found</code> 行を確認してください。</li>
    </ol>
  </div>
</main>
</body>
</html>
"""

class ThreadedHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True

RATE_LIMIT_LOCK = threading.Lock()
LAST_QUEUE_REQUESTS = {} # {ip: timestamp} URL追加用（最小間隔方式）
QUEUE_RATE_LIMIT_SECONDS = 2.5
UPLOAD_REQUEST_TIMES = {} # {ip: [timestamp, ...]} 写真アップロード用（時間枠内の合計枚数方式）
UPLOAD_RATE_LIMIT_BURST = 20    # 一括アップロードで許可する枚数
UPLOAD_RATE_LIMIT_WINDOW = 60.0 # 上記枚数を数える時間枠（秒）
MAX_REQUEST_BODY_BYTES = 64 * 1024
MAX_UPLOAD_BODY_BYTES = 20 * 1024 * 1024 # 20MB

def parse_multipart_file(body_bytes, content_type_header):
    """multipart/form-data からファイルバイナリとファイル名を取得"""
    m = re.search(r'boundary=([^;]+)', content_type_header)
    if not m:
        return None, None
    boundary = m.group(1).strip().strip('"').encode("utf-8")
    parts = body_bytes.split(b"--" + boundary)
    for part in parts:
        if b"filename=" in part:
            header_end = part.find(b"\r\n\r\n")
            if header_end == -1:
                header_end = part.find(b"\n\n")
                if header_end == -1:
                    continue
                body_start = header_end + 2
            else:
                body_start = header_end + 4
            headers_part = part[:header_end].decode("utf-8", errors="ignore")
            m_fn = re.search(r'filename="([^"]+)"', headers_part)
            filename = m_fn.group(1) if m_fn else "photo.jpg"
            file_data = part[body_start:].rstrip(b"\r\n--")
            return file_data, filename
    return None, None

class APIAndHLSHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, streamer_core=None, shutdown_callback=None, **kwargs):
        self.streamer_core = streamer_core
        self.shutdown_callback = shutdown_callback
        super().__init__(*args, directory=HLS_DIR, **kwargs)

    def _self_origins(self):
        """自分自身のオリジンとして認めるURLの集合"""
        port = self.streamer_core.config.get("port", 8000) if self.streamer_core else 8000
        origins = set()
        for host in ("127.0.0.1", "localhost", "[::1]"):
            origins.add(f"http://{host}:{port}")

        from streamer_core import get_local_ip
        local_ip = get_local_ip()
        origins.add(f"http://{local_ip}:{port}")

        raw_host = self.headers.get("Host", "")
        if raw_host:
            origins.add(f"http://{raw_host}")
            origins.add(f"https://{raw_host}")

        tunnel = (self.streamer_core.tunnel_raw_url if self.streamer_core else "") or ""
        if tunnel:
            origins.add(tunnel.rstrip("/"))
        return origins

    def _origin_is_self(self):
        """
        CSRF対策: Originヘッダが自分自身のオリジンか判定。
        ブラウザはPOSTに必ずOriginを付けるため、「Origin無し」= 非ブラウザ由来
        （VRCBeacon等のネイティブ/サーバサイドクライアント）とみなして許可する。
        """
        origin = self.headers.get("Origin")
        if origin is None:
            return True
        return origin.rstrip("/") in self._self_origins()

    def _host_header_is_safe(self):
        """
        DNSリビンディング対策: Hostヘッダがドメイン名の場合は拒否する。
        攻撃者ドメインを 127.0.0.1 に解決させる手口はHostが独自ドメインになるため弾ける。
        """
        raw_host = self.headers.get("Host", "")
        if not raw_host:
            return True
        hostname = urlparse(f"http://{raw_host}").hostname or ""
        hostname = hostname.lower()
        if hostname in ("localhost", ""):
            return True
        try:
            ipaddress.ip_address(hostname)
            return True  # IPリテラル直打ちはリビンディングの対象外
        except ValueError:
            pass
        tunnel = (self.streamer_core.tunnel_raw_url if self.streamer_core else "") or ""
        tunnel_host = (urlparse(tunnel).hostname or "").lower() if tunnel else ""
        return bool(tunnel_host) and hostname == tunnel_host

    def is_local_request(self):
        """
        ホストPC本人（＝停止・全消去などの破壊的操作を許してよい相手）か判定。

        既定はループバックのみ。トンネル無効時に同一LAN全体をホスト扱いしていた挙動は、
        同じWi-Fi上の任意の端末が /api/shutdown や clear_queue を叩けてしまうため撤廃した。
        従来どおりLAN内をホスト扱いしたい場合は config.json の
        "trust_lan_clients": true で明示的にオプトインする。
        なお LAN 端末は引き続き「ゲスト」として接続でき、
        allow_web_queue_add / allow_web_queue_edit / allow_web_playback_control の
        範囲でスマホからの追加・操作が可能（＝QR共有のワークフローは維持される）。
        """
        if "cf-connecting-ip" in self.headers or "x-forwarded-for" in self.headers:
            return False
        client_ip = self.client_address[0] if self.client_address else ""
        
        # ループバック判定
        is_loopback = client_ip in ("127.0.0.1", "::1", "localhost")
        
        # プライベートLAN判定 (192.168.x.x, 10.x.x.x, 172.16-31.x.x)
        is_private_lan = False
        try:
            ip_obj = ipaddress.ip_address(client_ip)
            is_private_lan = ip_obj.is_private or ip_obj.is_loopback
        except Exception:
            pass

        # 同一LANをホスト扱いするかどうかは明示的なオプトイン設定のみで決まる
        trust_lan = bool(
            self.streamer_core
            and self.streamer_core.config.get("trust_lan_clients", False)
        )

        if not is_loopback and not (trust_lan and is_private_lan):
            return False

        if not self._origin_is_self():
            log_print(f"[APIServer] Rejected local privilege: cross-site Origin {self.headers.get('Origin')!r}")
            return False
        if not self._host_header_is_safe():
            log_print(f"[APIServer] Rejected local privilege: suspicious Host {self.headers.get('Host')!r}")
            return False
        return True

    def check_rate_limit(self):
        """
        連投（DoS・スパム）防止レートリミット。
        キーにはCloudflareが上書きする CF-Connecting-IP か接続元IPのみを使う。
        X-Forwarded-For はクライアントが自由に詐称できるためキーに含めない。
        """
        client_ip = self.headers.get("cf-connecting-ip") or self.client_address[0]
        now = time.time()
        with RATE_LIMIT_LOCK:
            last_time = LAST_QUEUE_REQUESTS.get(client_ip, 0)
            if now - last_time < QUEUE_RATE_LIMIT_SECONDS:
                return False
            LAST_QUEUE_REQUESTS[client_ip] = now
            if len(LAST_QUEUE_REQUESTS) > 1000:
                for k in list(LAST_QUEUE_REQUESTS.keys()):
                    if now - LAST_QUEUE_REQUESTS[k] > 3600:
                        del LAST_QUEUE_REQUESTS[k]
            return True

    def check_upload_rate_limit(self):
        """
        写真アップロード用のレートリミット。

        URL追加と違い「複数枚をまとめて選ぶ」のが通常の使い方なので、最小間隔方式
        （2.5秒に1回）だとブラウザからの一括アップロードが2枚目以降すべて 429 になり、
        「1枚しかアップロードできない」状態になる。そのため一定時間内の合計枚数で
        制限する方式にして、連投防止は維持しつつ一括アップロードを通す。
        """
        client_ip = self.headers.get("cf-connecting-ip") or self.client_address[0]
        now = time.time()
        with RATE_LIMIT_LOCK:
            times = [t for t in UPLOAD_REQUEST_TIMES.get(client_ip, [])
                     if now - t < UPLOAD_RATE_LIMIT_WINDOW]
            if len(times) >= UPLOAD_RATE_LIMIT_BURST:
                UPLOAD_REQUEST_TIMES[client_ip] = times
                return False
            times.append(now)
            UPLOAD_REQUEST_TIMES[client_ip] = times
            if len(UPLOAD_REQUEST_TIMES) > 1000:
                for k in list(UPLOAD_REQUEST_TIMES.keys()):
                    stamps = UPLOAD_REQUEST_TIMES.get(k)
                    if not stamps or now - stamps[-1] > 3600:
                        del UPLOAD_REQUEST_TIMES[k]
            return True

    def send_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS, PUT, DELETE")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Requested-With")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")

    def send_json_response(self, status_code, data):
        response_bytes = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(response_bytes)))
        self.end_headers()
        self.wfile.write(response_bytes)

    def do_OPTIONS(self):
        self.send_response(204)
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        accept_header = self.headers.get("Accept", "")

        # 1. API: Status
        if path == "/api/status":
            if self.streamer_core:
                data = self.streamer_core.get_status_data()
            else:
                data = {"status": "offline", "error": "Core not initialized"}
            self.send_json_response(200, data)
            return

        # 2. API: Config (ローカルホストのみ許可)
        elif path == "/api/config":
            if not self.is_local_request():
                self.send_json_response(403, {"error": "Forbidden: Configuration access is restricted to localhost."})
                return
            if self.streamer_core:
                self.send_json_response(200, self.streamer_core.config)
            else:
                self.send_json_response(500, {"error": "Core not initialized"})
            return

        # 3. API: QR Code Image
        elif path == "/api/qrcode":
            url = ""
            if self.streamer_core and self.streamer_core.tunnel_raw_url:
                url = self.streamer_core.tunnel_raw_url
            elif self.streamer_core:
                port = self.streamer_core.config.get("port", 8000)
                url = f"http://localhost:{port}"
            else:
                url = "http://localhost:8000"

            try:
                import qrcode
                import io
                qr = qrcode.QRCode(version=1, box_size=6, border=2)
                qr.add_data(url)
                qr.make(fit=True)
                img = qr.make_image(fill_color="#0F172A", back_color="#FFFFFF")
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                png_data = buf.getvalue()

                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Length", str(len(png_data)))
                self.end_headers()
                self.wfile.write(png_data)
                return
            except Exception as e:
                log_print(f"[APIServer] Error generating QR image: {e}")
                self.send_json_response(500, {"error": "Failed to generate QR code"})
                return

        # 4. HTML Player (Root or /stream.m3u8 requested by browser)
        elif path == "/" or (path == "/stream.m3u8" and "text/html" in accept_header):
            live_sync = self.streamer_core.config.get("live_sync_duration_count", 4) if self.streamer_core else 4
            tunnel_stream_url = ""
            if self.streamer_core:
                if self.streamer_core.tunnel_url:
                    tunnel_stream_url = self.streamer_core.tunnel_url
                elif not self.streamer_core.enable_tunnel:
                    port = self.streamer_core.config.get("port", 8000)
                    tunnel_stream_url = f"http://localhost:{port}/stream.m3u8"
                else:
                    tunnel_stream_url = "(トンネルURL準備中...)"
            else:
                tunnel_stream_url = "(サーバー初期化中)"

            html = get_ui_html()
            html = html.replace("__LIVE_SYNC_DURATION_COUNT__", str(live_sync))
            html = html.replace("__TUNNEL_STREAM_URL__", tunnel_stream_url)
            content = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            return

        # 4. Static HLS files (SimpleHTTPRequestHandler fallback)
        super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        # 1. API: Photo Upload (写真・画像アップロード)
        if path == "/api/upload":
            if not self.is_local_request() and not self.streamer_core.config.get("allow_web_queue_add", True):
                self.send_json_response(403, {
                    "success": False,
                    "message": "Forbidden: Adding photos from Web is disabled by the host."
                })
                return

            if not self.is_local_request() and not self.check_upload_rate_limit():
                self.send_json_response(429, {
                    "success": False,
                    "message": (f"Rate limit exceeded: up to {UPLOAD_RATE_LIMIT_BURST} photos per "
                                f"{int(UPLOAD_RATE_LIMIT_WINDOW)} seconds. Please wait a moment.")
                })
                return

            try:
                content_len = int(self.headers.get("Content-Length", 0))
            except (TypeError, ValueError):
                content_len = 0

            if content_len <= 0 or content_len > MAX_UPLOAD_BODY_BYTES:
                self.send_json_response(413, {
                    "success": False,
                    "message": f"Invalid upload size or payload exceeds limit (max {MAX_UPLOAD_BODY_BYTES // (1024*1024)}MB)"
                })
                return

            if not self.streamer_core:
                self.send_json_response(500, {"success": False, "message": "Streamer core not available"})
                return

            body_bytes = self.rfile.read(content_len)
            content_type = self.headers.get("Content-Type", "")

            img_bytes, filename = None, "photo.jpg"
            if "multipart/form-data" in content_type:
                img_bytes, filename = parse_multipart_file(body_bytes, content_type)
            else:
                img_bytes = body_bytes
                filename = "uploaded_image.png"

            if not img_bytes:
                self.send_json_response(400, {"success": False, "message": "Could not parse image data from upload request"})
                return

            item = self.streamer_core.add_image_bytes(img_bytes, original_filename=filename)
            if item:
                self.send_json_response(200, {
                    "success": True,
                    "message": f"Successfully uploaded photo: {item.get('title')}",
                    "item": item
                })
            else:
                self.send_json_response(400, {
                    "success": False,
                    "message": "Failed to process image (unsupported image format or queue full)"
                })
            return

        # ボディ取得（JSON用サイズ上限 64KB）
        try:
            content_len = int(self.headers.get("Content-Length", 0))
        except (TypeError, ValueError):
            content_len = 0
        if content_len > MAX_REQUEST_BODY_BYTES:
            self.send_json_response(413, {
                "success": False,
                "message": f"Request body too large (max {MAX_REQUEST_BODY_BYTES} bytes)"
            })
            return
        body = self.rfile.read(content_len) if content_len > 0 else b"{}"
        try:
            body_json = json.loads(body.decode("utf-8")) if body else {}
        except Exception as e:
            log_print(f"[APIServer] Error parsing JSON body: {e}")
            body_json = {}

        log_print(f"[APIServer] POST {path} body: {body_json}")

        # 2. API: Queue (動画・画像URL追加)
        if path == "/api/queue":
            # 外部からの動画追加 許可チェック
            if not self.is_local_request() and not self.streamer_core.config.get("allow_web_queue_add", True):
                self.send_json_response(403, {
                    "success": False,
                    "message": "Forbidden: Adding items from Web is disabled by the host."
                })
                return

            # レートリミット判定 (外部からの連投・DoS防止)
            if not self.is_local_request() and not self.check_rate_limit():
                self.send_json_response(429, {
                    "success": False,
                    "message": "Rate limit exceeded. Please wait a few seconds before adding another item."
                })
                return

            url = body_json.get("url", "").strip()
            if not url:
                log_print("[APIServer] /api/queue missing url")
                self.send_json_response(400, {"success": False, "message": "Missing 'url' parameter in request body"})
                return

            if not self.streamer_core:
                self.send_json_response(500, {"success": False, "message": "Streamer core not available"})
                return

            items = self.streamer_core.add_to_queue(url)
            log_print(f"[APIServer] add_to_queue returned {len(items)} items")
            if items:
                self.send_json_response(200, {
                    "success": True,
                    "message": f"Successfully added {len(items)} item(s) to queue",
                    "video": items[0],
                    "items": items
                })
            else:
                self.send_json_response(400, {
                    "success": False,
                    "message": "Failed to resolve or add URL (check URL format, safety, or queue capacity)"
                })
            return

        # 3. API: Control (再生・キュー制御)
        elif path == "/api/control":
            action = body_json.get("action", "").strip().lower()
            if not self.streamer_core:
                self.send_json_response(500, {"success": False, "message": "Streamer core not available"})
                return

            is_local = self.is_local_request()

            # 破壊的・全消去操作は常にローカルホスト限定
            if action in ("clear_queue", "stop") and not is_local:
                self.send_json_response(403, {
                    "success": False,
                    "message": f"Forbidden: Action '{action}' is restricted to localhost."
                })
                return

            # キュー編集操作（削除・並び替え）の権限チェック
            if action in ("delete_item", "move_item") and not is_local:
                if not self.streamer_core.config.get("allow_web_queue_edit", True):
                    self.send_json_response(403, {
                        "success": False,
                        "message": "Forbidden: Queue editing from Web is disabled by the host."
                    })
                    return

            # 再生制御操作の権限チェック
            if action in ("skip", "prev", "set_loop", "set_shuffle", "shuffle", "toggle_image_pause", "set_image_pause", "set_image_duration", "set_image_auto_advance", "set_radio_mode", "set_radio_bg_source") and not is_local:
                if not self.streamer_core.config.get("allow_web_playback_control", True):
                    self.send_json_response(403, {
                        "success": False,
                        "message": "Forbidden: Playback control from Web is disabled by the host."
                    })
                    return

            if action == "skip":
                self.streamer_core.skip()
                self.send_json_response(200, {"success": True, "message": "Action 'skip' processed."})
            elif action == "prev":
                ok = self.streamer_core.play_prev()
                if ok:
                    self.send_json_response(200, {"success": True, "message": "Action 'prev' processed."})
                else:
                    self.send_json_response(400, {"success": False, "message": "No previous item in history."})
            elif action == "set_radio_mode":
                enabled = bool(body_json.get("enabled", True))
                res = self.streamer_core.set_radio_mode(enabled)
                self.send_json_response(200, {"success": True, "radio_mode": res, "message": f"Radio mode set to {res}."})
            elif action == "set_radio_bg_source":
                source = str(body_json.get("source", "card")).strip().lower()
                res = self.streamer_core.set_radio_bg_source(source)
                self.send_json_response(200, {"success": True, "radio_bg_source": res, "message": f"Radio background source set to {res}."})
            elif action == "toggle_image_pause":
                paused = self.streamer_core.toggle_image_pause()
                self.send_json_response(200, {"success": True, "image_paused": paused, "image_auto_advance": not paused, "message": f"Photo pause toggled to {paused}."})
            elif action == "set_image_pause":
                paused = bool(body_json.get("paused", True))
                self.streamer_core.set_image_pause(paused)
                self.send_json_response(200, {"success": True, "image_paused": paused, "image_auto_advance": not paused, "message": f"Photo pause set to {paused}."})
            elif action == "set_image_duration":
                duration = body_json.get("duration", 15)
                sec = self.streamer_core.set_image_duration(duration)
                self.send_json_response(200, {"success": True, "duration": sec, "message": f"Photo duration set to {sec}s."})
            elif action == "set_image_auto_advance":
                enabled = bool(body_json.get("enabled", True))
                self.streamer_core.set_image_auto_advance(enabled)
                self.send_json_response(200, {"success": True, "image_auto_advance": enabled, "image_paused": not enabled, "message": f"Photo auto advance set to {enabled}."})
            elif action == "clear_queue":
                self.streamer_core.clear_queue()
                self.send_json_response(200, {"success": True, "message": "Action 'clear_queue' processed."})
            elif action == "stop":
                self.streamer_core.clear_queue()
                self.streamer_core.skip()
                self.send_json_response(200, {"success": True, "message": "Action 'stop' processed (queue cleared and stream skipped)."})
            elif action == "delete_item":
                idx = body_json.get("index")
                if idx is not None and isinstance(idx, int):
                    deleted = self.streamer_core.delete_queue_item(idx)
                    if deleted:
                        self.send_json_response(200, {"success": True, "message": f"Item at index {idx} removed", "item": deleted})
                    else:
                        self.send_json_response(400, {"success": False, "message": f"Index {idx} out of range"})
                else:
                    self.send_json_response(400, {"success": False, "message": "Missing or invalid 'index' parameter"})
            elif action == "move_item":
                from_idx = body_json.get("from_index")
                to_idx = body_json.get("to_index")
                if from_idx is not None and to_idx is not None:
                    ok = self.streamer_core.move_queue_item(int(from_idx), int(to_idx))
                    if ok:
                        self.send_json_response(200, {"success": True, "message": "Item moved successfully."})
                    else:
                        self.send_json_response(400, {"success": False, "message": "Invalid index range."})
                else:
                    self.send_json_response(400, {"success": False, "message": "Missing 'from_index' or 'to_index'"})
            elif action == "shuffle":
                self.streamer_core.shuffle_queue()
                self.send_json_response(200, {"success": True, "message": "Queue shuffled successfully."})
            elif action == "set_loop":
                enabled = body_json.get("enabled", True)
                res = self.streamer_core.set_loop(enabled)
                self.send_json_response(200, {"success": True, "loop_queue": res, "message": f"Loop queue set to {res}."})
            elif action == "set_shuffle":
                enabled = body_json.get("enabled", True)
                res = self.streamer_core.set_shuffle(enabled)
                self.send_json_response(200, {"success": True, "shuffle": res, "message": f"Shuffle set to {res}."})
            else:
                self.send_json_response(400, {
                    "success": False,
                    "message": f"Unknown action: '{action}'."
                })
            return

        # 3. API: Config (ローカルホスト限定)
        elif path == "/api/config":
            if not self.is_local_request():
                self.send_json_response(403, {"success": False, "message": "Forbidden: Configuration changes are restricted to localhost."})
                return
            if not self.streamer_core:
                self.send_json_response(500, {"success": False, "message": "Streamer core not available"})
                return
            saved = self.streamer_core.save_config(body_json)
            if saved:
                self.send_json_response(200, {"success": True, "config": self.streamer_core.config})
            else:
                self.send_json_response(500, {"success": False, "message": "Failed to save configuration"})
            return

        # 4. API: Shutdown (ローカルホスト限定)
        elif path == "/api/shutdown":
            if not self.is_local_request():
                self.send_json_response(403, {"success": False, "message": "Forbidden: Shutdown command is restricted to localhost."})
                return
            self.send_json_response(200, {"success": True, "message": "Server is shutting down..."})
            if self.shutdown_callback:
                threading.Thread(target=self.shutdown_callback, daemon=True).start()
            return

        else:
            self.send_json_response(404, {"error": "Not Found", "path": path})

    def end_headers(self):
        self.send_cors_headers()
        super().end_headers()

    def log_message(self, format, *args):
        # ログの抑制 (必要に応じてデバッグログ化)
        pass

class APIServer:
    def __init__(self, streamer_core, on_shutdown=None):
        self.streamer_core = streamer_core
        self.on_shutdown = on_shutdown
        self.httpd = None
        self.server_thread = None

    def create_handler(self, *args, **kwargs):
        return APIAndHLSHandler(*args, streamer_core=self.streamer_core,
                                shutdown_callback=self._trigger_shutdown, **kwargs)

    def _trigger_shutdown(self):
        time.sleep(0.5)
        if self.on_shutdown:
            self.on_shutdown()
        else:
            self.stop()
            if self.streamer_core:
                self.streamer_core.shutdown()
            sys.exit(0)

    def start(self):
        port = self.streamer_core.config.get("port", 8000)
        host = self.streamer_core.config.get("host", "127.0.0.1")

        # config の host をそのまま尊重する。
        # 以前はトンネル無効時に host 設定を無視して全インターフェースへバインドしており、
        # "127.0.0.1" 指定でも実際は 0.0.0.0 で待ち受けていた（ログ表示も実態と食い違っていた）。
        # LAN公開したい場合は host を "0.0.0.0" にするか、起動時に --host 0.0.0.0 を渡す。
        bind_host = "" if host in ("0.0.0.0", "") else host
        listens_on_all = bind_host == ""

        from streamer_core import get_local_ip
        local_ip = get_local_ip()

        try:
            self.httpd = ThreadedHTTPServer((bind_host, port), self.create_handler)
            endpoints = f"Local: http://127.0.0.1:{port}"
            if listens_on_all:
                endpoints += f", LAN: http://{local_ip}:{port}"
            log_print(f"[APIServer] Listening on {'0.0.0.0' if listens_on_all else host}:{port} ({endpoints})")
            if listens_on_all:
                trust_lan = bool(self.streamer_core.config.get("trust_lan_clients", False))
                log_print(
                    "[APIServer] Bound to ALL interfaces. LAN clients are treated as "
                    + ("HOSTS (trust_lan_clients=true)" if trust_lan
                       else "guests (allow_web_* permissions apply)")
                )
            self.server_thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
            self.server_thread.start()
            return True
        except Exception as e:
            log_print(f"[APIServer] Failed to bind on {host}:{port}: {e}")
            return False

    def stop(self):
        if self.httpd:
            log_print("[APIServer] Stopping HTTP server...")
            try:
                self.httpd.shutdown()
                self.httpd.server_close()
            except Exception:
                pass
            self.httpd = None
