import os, sys, time, re, threading, subprocess, http.server, socketserver, yt_dlp, io

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

PORT = 8000
HLS_DIR = os.path.abspath("hls_output")
CLOUDFLARED_EXE = "cloudflared.exe"
os.makedirs(HLS_DIR, exist_ok=True)

hls_proc = None
send_proc = None
current_stdin = None

play_queue = []
queue_lock = threading.Lock()
process_lock = threading.Lock()
current_video_title = "None"

skip_event = threading.Event()
video_done_event = threading.Event()


HTML_PLAYER = """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>VRCYouTube Stream Web Player</title>
    <script src="https://cdn.jsdelivr.net/npm/hls.js@latest"></script>
    <style>
        body {
            background-color: #121212;
            color: #ffffff;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            min-height: 100vh;
            margin: 0;
            padding: 20px;
            box-sizing: border-box;
        }
        .container {
            text-align: center;
            max-width: 800px;
            width: 100%;
        }
        h1 {
            color: #3b82f6;
            margin-bottom: 20px;
            font-size: 24px;
        }
        .video-wrapper {
            position: relative;
            padding-bottom: 56.25%; /* 16:9 Aspect Ratio */
            height: 0;
            background-color: #000;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.3), 0 4px 6px -2px rgba(0, 0, 0, 0.05);
        }
        video {
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
        }
        .status {
            margin-top: 20px;
            padding: 12px;
            border-radius: 6px;
            background-color: #1e293b;
            font-size: 14px;
            font-weight: 500;
            transition: background-color 0.3s;
            cursor: pointer;
        }
        .info-box {
            margin-top: 20px;
            padding: 15px;
            border-radius: 6px;
            background-color: #1e1e1e;
            border: 1px solid #2d2d2d;
            font-size: 13px;
            line-height: 1.5;
            color: #a3a3a3;
            text-align: left;
        }
        .info-box code {
            display: block;
            background-color: #2d2d2d;
            color: #3b82f6;
            padding: 8px 12px;
            border-radius: 4px;
            margin-top: 8px;
            word-break: break-all;
            user-select: all;
            font-family: monospace;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>VRCYouTube Web Player</h1>
        <div class="video-wrapper">
            <video id="video" controls autoplay playsinline></video>
        </div>
        <div id="status" class="status">Checking stream status...</div>
        <div class="info-box">
            VRChat内で視聴する場合は、以下のストリームURLを動画プレイヤー（iwaSync3, YPlay, ProTV等）に設定してください：
            <code id="hls-url">Loading...</code>
        </div>
    </div>

    <script>
        const video = document.getElementById('video');
        const statusDiv = document.getElementById('status');
        const hlsUrlSpan = document.getElementById('hls-url');
        const streamUrl = window.location.origin + '/stream.m3u8';
        hlsUrlSpan.textContent = streamUrl;

        // Video event listeners for accurate status reporting
        video.addEventListener('playing', () => {
            statusDiv.textContent = "配信中 / Stream Active (Playing)";
            statusDiv.style.backgroundColor = "#047857";
        });
        video.addEventListener('pause', () => {
            statusDiv.textContent = "一時停止中 / Paused";
            statusDiv.style.backgroundColor = "#4b5563";
        });
        video.addEventListener('waiting', () => {
            statusDiv.textContent = "バッファリング中 / Buffering...";
            statusDiv.style.backgroundColor = "#b45309";
        });

        // Click on status bar to trigger play (helpful for blocked autoplay)
        statusDiv.addEventListener('click', () => {
            if (video.paused) {
                video.play().catch(e => console.log("Play failed:", e));
            }
        });

        function checkStream() {
            fetch(streamUrl, { method: 'HEAD' })
                .then(response => {
                    if (response.ok) {
                        statusDiv.textContent = "配信中 / Stream Active (Loading...)";
                        statusDiv.style.backgroundColor = "#065f46";
                        initPlayer();
                    } else {
                        statusDiv.textContent = "配信オフライン / Stream Offline (キューが空です)";
                        statusDiv.style.backgroundColor = "#991b1b";
                        destroyPlayer();
                        setTimeout(checkStream, 3000);
                    }
                })
                .catch(() => {
                    statusDiv.textContent = "配信オフライン / Stream Offline (接続エラー)";
                    statusDiv.style.backgroundColor = "#991b1b";
                    destroyPlayer();
                    setTimeout(checkStream, 3000);
                });
        }

        let hls = null;
        function initPlayer() {
            if (hls || video.src) return; // already initialized
            
            if (Hls.isSupported()) {
                hls = new Hls({
                    maxBufferLength: 30,
                    liveSyncDurationCount: 4, // Buffers 4 segments (approx 12s) behind live edge for stability
                    manifestLoadingMaxRetry: 10,
                    manifestLoadingRetryDelay: 1000,
                    levelLoadingMaxRetry: 10,
                    levelLoadingRetryDelay: 1000,
                    fragLoadingMaxRetry: 10,
                    fragLoadingRetryDelay: 1000
                });
                hls.loadSource(streamUrl);
                hls.attachMedia(video);
                hls.on(Hls.Events.MANIFEST_PARSED, function() {
                    video.play().catch(e => {
                        statusDiv.textContent = "配信中 (クリックして再生を開始してください)";
                        console.log("Auto-play blocked:", e);
                    });
                });
                hls.on(Hls.Events.ERROR, function(event, data) {
                    if (data.fatal) {
                        console.warn("HLS fatal error:", data.type);
                        destroyPlayer();
                        setTimeout(checkStream, 2000);
                    }
                });
            } else if (video.canPlayType('application/vnd.apple.mpegurl')) {
                video.src = streamUrl;
                video.addEventListener('loadedmetadata', function() {
                    video.play().catch(e => {
                        statusDiv.textContent = "配信中 (クリックして再生を開始してください)";
                        console.log("Auto-play blocked:", e);
                    });
                });
            }
        }

        function destroyPlayer() {
            if (hls) {
                hls.destroy();
                hls = null;
            }
            video.src = "";
            video.load();
        }

        checkStream();
    </script>
</body>
</html>
"""


class HLSAccessHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=HLS_DIR, **kwargs)

    def do_GET(self):
        accept_header = self.headers.get('Accept', '')
        # If accessed from a web browser (which expects HTML), serve the player page instead of directory listing or 404
        if self.path == '/' or (self.path == '/stream.m3u8' and 'text/html' in accept_header):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_PLAYER.encode('utf-8'))
            return
        super().do_GET()

    def end_headers(self):
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        self.send_header("Access-Control-Allow-Origin", "*")
        super().end_headers()

    def log_message(self, format, *args):
        pass


def run_server():
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", PORT), HLSAccessHandler) as httpd:
        print(f"HLS Server running on port {PORT}...", flush=True)
        httpd.serve_forever()


def expand_playlist(url):
    print(f"Analyzing URL: {url}", flush=True)
    ydl_opts = {"extract_flat": True, "skip_download": True, "quiet": True}
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if "entries" in info:
                entries = list(info["entries"])
                print(f"Playlist: {info.get('title','?')} ({len(entries)} items)", flush=True)
                return [(f"https://www.youtube.com/watch?v={e['id']}", e.get("title","?")) for e in entries if e]
            else:
                return [(url, info.get("title", "No Title"))]
    except Exception as e:
        print(f"Failed to analyze URL: {e}", flush=True)
        return []


def get_stream_urls(youtube_url):
    ydl_opts = {
        "format": "bestvideo[vcodec^=avc1]+bestaudio[acodec^=mp4a]/best[vcodec^=avc1]/best",
        "quiet": True,
        "nocheckcertificate": True,
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
        return video_url, audio_url, info.get("title", "Unknown"), headers


def kill_proc(proc):
    if not proc:
        return
    try:
        proc.kill()
    except Exception:
        pass


def start_hls_receiver():
    """動画ごとに新しいHLS受信FFmpegを起動する"""
    global hls_proc, current_stdin

    # 旧プロセスを停止
    if hls_proc:
        kill_proc(hls_proc)
        hls_proc = None
        time.sleep(0.5)

    cmd = [
        "ffmpeg", "-y",
        "-i", "pipe:0",
        "-c:v", "copy",
        "-c:a", "copy",
        "-f", "hls",
        "-hls_time", "3",
        "-hls_list_size", "10",
        "-hls_flags", "delete_segments+append_list",
        "-hls_segment_filename", os.path.join(HLS_DIR, "seg_%03d.ts"),
        os.path.join(HLS_DIR, "stream.m3u8"),
    ]
    hls_proc = subprocess.Popen(cmd, stdin=subprocess.PIPE,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    current_stdin = hls_proc.stdin
    print("[Receiver] HLS FFmpeg started.", flush=True)


def relay_stream_data(proc_to_read, stdin_to_write, stop_event):
    try:
        while not stop_event.is_set():
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
            video_done_event.set()


def watch_send_proc(proc, stop_event):
    try:
        proc.wait()
    except Exception:
        pass
    if not stop_event.is_set():
        print("[Monitor] Video finished naturally.", flush=True)
        video_done_event.set()


def play_video(youtube_url):
    global send_proc, current_video_title
    try:
        video_url, audio_url, title, headers = get_stream_urls(youtube_url)
        current_video_title = title
        print(f"\n[Player] Now Playing: {title}", flush=True)
    except Exception as e:
        print(f"[Player] Failed to get stream URL: {e}", flush=True)
        return None

    # 受信側FFmpegを再起動（タイムスタンプリセット）
    start_hls_receiver()

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

    cmd = ["ffmpeg", "-re", "-fflags", "+genpts"]
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

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                             stderr=subprocess.DEVNULL, bufsize=0)
    with process_lock:
        send_proc = proc

    stop_event = threading.Event()
    threading.Thread(target=relay_stream_data,
                     args=(proc, current_stdin, stop_event), daemon=True).start()
    threading.Thread(target=watch_send_proc,
                     args=(proc, stop_event), daemon=True).start()
    return stop_event


def skip_current_video():
    global send_proc
    print("[Player] Skipping...", flush=True)
    skip_event.set()
    video_done_event.set()
    with process_lock:
        proc = send_proc
    if proc:
        kill_proc(proc)


def queue_monitor():
    global send_proc, current_video_title
    print("[Monitor] Queue monitor started.", flush=True)
    while True:
        try:
            next_url = next_title = None
            with queue_lock:
                if play_queue:
                    next_url, next_title = play_queue.pop(0)

            if not next_url:
                current_video_title = "Queue Empty"
                time.sleep(1)
                continue

            print(f"[Monitor] Loading: {next_title}", flush=True)
            skip_event.clear()
            video_done_event.clear()

            stop_event = play_video(next_url)
            if stop_event is None:
                print("[Monitor] Failed to play. Skipping.", flush=True)
                continue

            # 終了 or スキップを待つ
            while True:
                if video_done_event.wait(timeout=0.5):
                    break
                with process_lock:
                    proc = send_proc
                    h_proc = hls_proc
                if proc and proc.poll() is not None:
                    break
                if h_proc and h_proc.poll() is not None:
                    print("[Monitor] Receiver FFmpeg crashed or exited.", flush=True)
                    break

            # 自然終了（スキップではない）の場合、最後のバッファをプレイヤーが再生しきるまで5秒待つ
            if not skip_event.is_set():
                print("[Monitor] Waiting 5 seconds for player to finish buffer...", flush=True)
                time.sleep(5)

            stop_event.set()
            with process_lock:
                proc = send_proc
                if proc:
                    kill_proc(proc)
                send_proc = None

            if skip_event.is_set():
                print("[Monitor] Skipped.", flush=True)
                skip_event.clear()
            video_done_event.clear()

        except Exception as e:
            print(f"[Monitor] Exception: {e}", flush=True)
            time.sleep(1)


def start_tunnel():
    print("Starting Cloudflare Quick Tunnel...", flush=True)
    cmd = [os.path.abspath(CLOUDFLARED_EXE), "tunnel", "--url", f"http://localhost:{PORT}"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, encoding="utf-8", errors="replace")
    tunnel_url = None
    t0 = time.time()
    while time.time() - t0 < 30:
        line = proc.stderr.readline()
        if not line:
            break
        m = re.search(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com", line)
        if m:
            tunnel_url = m.group(0)
            print(f"\n==================================================")
            print(f"Cloudflare Tunnel Established!")
            print(f"HLS Stream URL for VRChat:")
            print(f"  {tunnel_url}/stream.m3u8")
            print(f"==================================================")
            sys.stdout.flush()
            break
    threading.Thread(target=lambda: [_ for _ in proc.stderr], daemon=True).start()
    return proc, tunnel_url


if __name__ == "__main__":
    threading.Thread(target=run_server, daemon=True).start()
    time.sleep(1)

    tunnel_proc, tunnel_url = start_tunnel()
    if not tunnel_url:
        print("Tunnel failed.", flush=True)
        sys.exit(1)

    threading.Thread(target=queue_monitor, daemon=True).start()

    print("\n--- Control Panel ---", flush=True)
    print("  add [URL]  : Add video/playlist", flush=True)
    print("  skip       : Skip current video", flush=True)
    print("  list       : Show queue", flush=True)
    print("  exit       : Quit", flush=True)
    print("---------------------\n", flush=True)

    # No default video in queue (starts empty)

    while True:
        try:
            inp = input("Command: ").strip()
            if not inp:
                continue
            if inp.lower() == "exit":
                break
            elif inp.lower() == "skip":
                skip_current_video()
            elif inp.lower() == "list":
                with queue_lock:
                    print(f"\n--- Queue ({len(play_queue)} items) ---", flush=True)
                    print(f"Now Playing: {current_video_title}", flush=True)
                    for i, (u, t) in enumerate(play_queue, 1):
                        print(f"  {i}. {t}", flush=True)
                    print("------\n", flush=True)
            elif inp.lower().startswith("add "):
                url = inp[4:].strip()
                def do_add(u):
                    items = expand_playlist(u)
                    if items:
                        with queue_lock:
                            play_queue.extend(items)
                        print(f"\n[Queue] Added {len(items)} item(s).\nCommand: ", end="", flush=True)
                    else:
                        print(f"\n[Queue] No items added.\nCommand: ", end="", flush=True)
                threading.Thread(target=do_add, args=(url,), daemon=True).start()
            else:
                print("Unknown command.", flush=True)
        except KeyboardInterrupt:
            break

    print("Shutting down...", flush=True)
    with process_lock:
        kill_proc(send_proc)
        kill_proc(hls_proc)
    tunnel_proc.terminate()
