import os
import sys
import time
import re
import threading
import subprocess
import http.server
import socketserver
import urllib.request
import yt_dlp

PORT = 8000
HLS_DIR = os.path.abspath("hls_output")
CLOUDFLARED_EXE = "cloudflared.exe"

# HLS出力用ディレクトリの作成
os.makedirs(HLS_DIR, exist_ok=True)

class HLSAccessHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        # 指定ディレクトリから配信するように設定
        super().__init__(*args, directory=HLS_DIR, **kwargs)

    def end_headers(self):
        # キャッシュ無効化ヘッダーを付与
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        # CORSを許可（VRChatからのアクセス用）
        self.send_header("Access-Control-Allow-Origin", "*")
        super().end_headers()

def run_server():
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", PORT), HLSAccessHandler) as httpd:
        print(f"HLS Server running on port {PORT}...")
        httpd.serve_forever()

def get_stream_urls(youtube_url):
    print(f"Analyzing YouTube URL: {youtube_url}")
    ydl_opts = {
        'format': 'bestvideo[vcodec^=avc1]+bestaudio[acodec^=mp4a]/best[vcodec^=avc1]/best',
        'quiet': True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(youtube_url, download=False)
        # もしフォーマットが結合されておらず、個別のビデオ/オーディオURLがある場合
        video_url = None
        audio_url = None
        
        # 簡易的に、yt-dlpが選択したフォーマットを取得
        if 'requested_formats' in info:
            for fmt in info['requested_formats']:
                if fmt.get('vcodec') != 'none' and fmt.get('acodec') == 'none':
                    video_url = fmt.get('url')
                elif fmt.get('acodec') != 'none' and fmt.get('vcodec') == 'none':
                    audio_url = fmt.get('url')
        
        if not video_url or not audio_url:
            # フォールバック: 単一のストリーム
            video_url = info.get('url')
            audio_url = None
            
        return video_url, audio_url, info.get('title', 'Unknown Title')

def start_ffmpeg(video_url, audio_url):
    print("Starting FFmpeg HLS encoding...")
    # 古いHLSファイルを削除
    for f in os.listdir(HLS_DIR):
        if f.endswith(".ts") or f.endswith(".m3u8"):
            try:
                os.remove(os.path.join(HLS_DIR, f))
            except Exception:
                pass

    # FFmpegコマンドの組み立て
    # ビデオはコピー(負荷ほぼゼロ)、オーディオは念のためAACに再エンコード
    cmd = [
        "ffmpeg",
        "-re", # リアルタイム読み込み
        "-i", video_url
    ]
    if audio_url:
        cmd.extend(["-i", audio_url])
        
    cmd.extend([
        "-map", "0:v:0"
    ])
    if audio_url:
        cmd.extend(["-map", "1:a:0"])
    else:
        cmd.extend(["-map", "0:a:0?"])

    # 負荷を下げるため映像は再エンコードせずコピー (-c:v copy)
    # 音声は VRChat の互換性のために AAC へエンコード (-c:a aac)
    cmd.extend([
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "128k",
        "-f", "hls",
        "-hls_time", "2",              # 各セグメントの長さ（秒）。低遅延化のため短めに
        "-hls_list_size", "5",         # プレイリストに残すセグメント数
        "-hls_flags", "delete_segments", # 古いセグメントを自動削除してディスク負荷を低減
        "-hls_segment_filename", os.path.join(HLS_DIR, "seg_%03d.ts"),
        os.path.join(HLS_DIR, "stream.m3u8")
    ])
    
    process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, encoding="utf-8")
    return process

def log_stream(stream, label):
    try:
        with stream:
            for line in iter(stream.readline, ''):
                # 起動時の進捗などを見せるため、FFmpegのエラー出力をコンソールに流す
                if "Error" in line or "warning" in line or "Output" in line:
                    print(f"[{label}] {line.strip()}", flush=True)
    except Exception:
        pass

def start_tunnel():
    print("Starting Cloudflare Quick Tunnel...")
    cmd = [os.path.abspath(CLOUDFLARED_EXE), "tunnel", "--url", f"http://localhost:{PORT}"]
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8")
    
    tunnel_url = None
    start_time = time.time()
    while time.time() - start_time < 30:
        line = process.stderr.readline()
        if not line:
            break
        match = re.search(r'https://[a-zA-Z0-9-]+\.trycloudflare\.com', line)
        if match:
            tunnel_url = match.group(0)
            print(f"\n==================================================")
            print(f"Cloudflare Tunnel Established!")
            print(f"HLS Stream URL for VRChat:")
            print(f"  {tunnel_url}/stream.m3u8")
            print(f"==================================================\n", flush=True)
            break
            
    # ストリームをフラッシュ
    threading.Thread(target=log_stream, args=(process.stderr, "tunnel"), daemon=True).start()
    return process, tunnel_url

if __name__ == "__main__":
    youtube_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    if len(sys.argv) > 1:
        youtube_url = sys.argv[1]
        
    # 1. サーバー起動
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    time.sleep(1)
    
    # 2. トンネル起動
    tunnel_proc, url = start_tunnel()
    if not url:
        print("Failed to start tunnel.")
        sys.exit(1)
        
    # 3. YouTube URL解析
    try:
        video_url, audio_url, title = get_stream_urls(youtube_url)
        print(f"Playing Title: {title}")
    except Exception as e:
        print(f"Failed to analyze URL: {e}")
        tunnel_proc.terminate()
        sys.exit(1)
        
    # 4. FFmpeg起動
    ffmpeg_proc = start_ffmpeg(video_url, audio_url)
    threading.Thread(target=log_stream, args=(ffmpeg_proc.stderr, "ffmpeg"), daemon=True).start()
    
    print("\nStream started! Enter 'exit' to stop.")
    while True:
        try:
            inp = input("> ")
            if inp.strip().lower() == "exit":
                break
        except KeyboardInterrupt:
            break
            
    print("Stopping stream, tunnel and server...")
    ffmpeg_proc.terminate()
    tunnel_proc.terminate()
    try:
        ffmpeg_proc.wait(timeout=3)
        tunnel_proc.wait(timeout=3)
    except Exception:
        pass
    print("Done.")
