import http.server
import socketserver
import threading
import time
import urllib.request
import os
import subprocess
import re

PORT = 8000
# URLリストを保持
playlist_urls = ["https://www.youtube.com/watch?v=dQw4w9WgXcQ"]
CLOUDFLARED_EXE = "cloudflared.exe"
CLOUDFLARED_URL = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"

class PlaylistHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def do_HEAD(self):
        self.handle_request(is_head=True)

    def do_GET(self):
        self.handle_request(is_head=False)

    def handle_request(self, is_head=False):
        global playlist_urls
        path = self.path.split('?')[0] # クエリパラメータを除外
        
        # リクエストヘッダーのログ出力
        print(f"\n--- Incoming Request: {self.command} {self.path} ---")
        for key, value in self.headers.items():
            print(f"  {key}: {value}")
        print("-------------------------------------------\n", flush=True)
        
        if path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            
            # Simple landing page listing all the formats
            html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>VRCYouTube Test Playlist Server</title>
    <style>
        body {{
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
        .container {{
            max-width: 600px;
            width: 100%;
            background-color: #1e1e1e;
            padding: 30px;
            border-radius: 8px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        }}
        h1 {{
            color: #3b82f6;
            margin-top: 0;
            font-size: 22px;
        }}
        ul {{
            list-style: none;
            padding: 0;
        }}
        li {{
            margin-bottom: 15px;
            background-color: #2d2d2d;
            padding: 12px;
            border-radius: 6px;
        }}
        .format-name {{
            font-weight: bold;
            color: #60a5fa;
            margin-bottom: 4px;
        }}
        a {{
            color: #3b82f6;
            text-decoration: none;
            word-break: break-all;
            font-family: monospace;
        }}
        a:hover {{
            text-decoration: underline;
        }}
        .urls-list {{
            margin-top: 20px;
            padding: 10px;
            background-color: #121212;
            border-radius: 4px;
            font-size: 13px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>VRCYouTube Test Playlist Server</h1>
        <p>以下のURLをコピーしてVRChat等の動画プレイヤーに設定してください：</p>
        <ul>
            <li>
                <div class="format-name">Plain Text 形式</div>
                <a href="/playlist.txt">/playlist.txt</a>
            </li>
            <li>
                <div class="format-name">M3U 形式 (m3u8)</div>
                <a href="/playlist.m3u">/playlist.m3u</a> (.m3u8 でも可能)
            </li>
            <li>
                <div class="format-name">ProTV JSON 形式</div>
                <a href="/playlist.playlist">/playlist.playlist</a>
            </li>
        </ul>
        <h3>現在のプレイリスト登録URL:</h3>
        <div class="urls-list">
            {"<br>".join(playlist_urls)}
        </div>
    </div>
</body>
</html>
"""
            if not is_head:
                self.wfile.write(html.encode("utf-8"))
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {self.command} {path} - Served HTML Landing Page")

        elif path in ("/playlist.txt", "/playlist.m3u", "/playlist.m3u8", "/playlist.playlist"):
            self.send_response(200)
            
            # キャッシュ無効化ヘッダー
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
            
            response_body = ""
            # VRChatがストリームとして誤認識するのを防ぐため、プレイリストファイルは text/plain で統一して返す
            content_type = "text/plain; charset=utf-8"
            
            if path in ("/playlist.m3u", "/playlist.m3u8"):
                lines = ["#EXTM3U"]
                for url in playlist_urls:
                    lines.append(f"#EXTINF:-1,Video")
                    lines.append(url)
                response_body = "\n".join(lines) + "\n"
                
            elif path == "/playlist.playlist":
                # ProTV JSON形式の場合は application/json とするが、テキストダウンロードなら text/plain の方が安全な場合もある
                content_type = "application/json; charset=utf-8"
                protv_data = {
                    "header": "VRCYouTube Test Playlist",
                    "items": [{"title": f"Video {i+1}", "url": url} for i, url in enumerate(playlist_urls)]
                }
                import json
                response_body = json.dumps(protv_data, indent=2, ensure_ascii=False)
                
            else: # /playlist.txt
                response_body = "\n".join(playlist_urls) + "\n"
                
            response_bytes = response_body.encode("utf-8")
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(response_bytes)))
            self.end_headers()
            
            if not is_head:
                self.wfile.write(response_bytes)
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {self.command} {path} - Served (len: {len(response_bytes)})")
        else:
            self.send_error(404, "File not found")

def download_cloudflared():
    if not os.path.exists(CLOUDFLARED_EXE):
        print("cloudflared.exe not found. Downloading from GitHub...")
        try:
            urllib.request.urlretrieve(CLOUDFLARED_URL, CLOUDFLARED_EXE)
            print("Successfully downloaded cloudflared.exe.")
        except Exception as e:
            print(f"Failed to download cloudflared.exe: {e}")
            return False
    return True

def run_server():
    handler = PlaylistHTTPRequestHandler
    # 複数回起動時のポートバインド競合を防ぐため allow_reuse_address を有効化
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", PORT), handler) as httpd:
        print(f"Starting local server on port {PORT}...")
        httpd.serve_forever()

def log_stream(stream, label):
    try:
        with stream:
            for line in iter(stream.readline, ''):
                # デバッグ用に非表示にするか、ログに流す
                # VRChatからのアクセスの様子などが見えるように、接続ログ以外のデバッグ用に出力しておく
                print(f"[{label}] {line.strip()}", flush=True)
    except Exception:
        pass

def start_tunnel():
    if not download_cloudflared():
        print("Skipping Cloudflare Tunnel because cloudflared.exe is missing.")
        return None

    print("Starting Cloudflare Quick Tunnel...")
    # --url http://localhost:8000 でトンネルを開始
    cmd = [os.path.abspath(CLOUDFLARED_EXE), "tunnel", "--url", f"http://localhost:{PORT}"]
    
    # stdout/stderr のバッファ詰まりを防ぐため
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8")
    
    # トンネルURLが発行されるのを待つ (xxx.trycloudflare.com)
    tunnel_url = None
    start_time = time.time()
    
    # 一旦メインスレッドでURLが見つかるまで一行ずつ読む
    lines_read = []
    while time.time() - start_time < 30: # 最大30秒待機
        line = process.stderr.readline()
        if not line:
            break
        lines_read.append(line)
        match = re.search(r'https://[a-zA-Z0-9-]+\.trycloudflare\.com', line)
        if match:
            tunnel_url = match.group(0)
            print(f"\n==================================================")
            print(f"Cloudflare Tunnel Established!")
            print(f"  Plain Text: {tunnel_url}/playlist.txt")
            print(f"  M3U Format: {tunnel_url}/playlist.m3u (or .m3u8)")
            print(f"  ProTV JSON: {tunnel_url}/playlist.playlist")
            print(f"==================================================\n", flush=True)
            break
            
    if not tunnel_url:
        print("Failed to retrieve Cloudflare Tunnel URL within timeout.")
        # 読み取った行を出力してエラー原因を探る
        print("--- cloudflared startup logs ---")
        for l in lines_read:
            print(l.strip())
        print("--------------------------------")
    
    # 残りのストリームを別スレッドで読み続けてデッドロックを防ぐ
    threading.Thread(target=log_stream, args=(process.stderr, "cloudflared-err"), daemon=True).start()
    threading.Thread(target=log_stream, args=(process.stdout, "cloudflared-out"), daemon=True).start()
    
    return process

if __name__ == "__main__":
    # サーバーを別スレッドで起動
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    
    time.sleep(1)
    
    # トンネルを起動
    tunnel_process = start_tunnel()
    
    print("\n--- Control Panel ---")
    print("Type new playlist content (comma separated YouTube URLs) and press Enter to update playlist.")
    print("Type 'exit' to stop server and tunnel.\n")
    
    while True:
        try:
            user_input = input("Update URLs (or 'exit'): ")
            if user_input.strip().lower() == "exit":
                break
            
            # 入力されたURLをリストに変換
            urls = [url.strip() for url in user_input.split(",") if url.strip()]
            if urls:
                playlist_urls = urls
                print(f"Updated playlist URLs:\n" + "\n".join(playlist_urls))
            else:
                print("Invalid input.")
        except KeyboardInterrupt:
            break
            
    print("Stopping tunnel and server...")
    if tunnel_process:
        tunnel_process.terminate()
        try:
            tunnel_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            tunnel_process.kill()

