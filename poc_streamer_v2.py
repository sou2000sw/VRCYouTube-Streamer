import os
import sys
import time
import re
import threading
import subprocess
import http.server
import socketserver
import yt_dlp

PORT = 8000
HLS_DIR = os.path.abspath("hls_output")
CLOUDFLARED_EXE = "cloudflared.exe"

os.makedirs(HLS_DIR, exist_ok=True)

# グローバル制御用
ffmpeg_proc = None
ffmpeg_lock = threading.Lock()

class HLSAccessHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=HLS_DIR, **kwargs)

    def end_headers(self):
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
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
        video_url = None
        audio_url = None
        
        if 'requested_formats' in info:
            for fmt in info['requested_formats']:
                if fmt.get('vcodec') != 'none' and fmt.get('acodec') == 'none':
                    video_url = fmt.get('url')
                elif fmt.get('acodec') != 'none' and fmt.get('vcodec') == 'none':
                    audio_url = fmt.get('url')
        
        if not video_url or not audio_url:
            video_url = info.get('url')
            audio_url = None
            
        return video_url, audio_url, info.get('title', 'Unknown Title')

def log_stream(stream, label):
    try:
        with stream:
            for line in iter(stream.readline, ''):
                # ログ確認用
                if "Error" in line or "warning" in line or "Output" in line or "frame=" in line[:6]:
                    # 進行状況もたまに出力
                    print(f"[{label}] {line.strip()}", flush=True)
    except Exception:
        pass

def start_ffmpeg(video_url, audio_url):
    global ffmpeg_proc
    with ffmpeg_lock:
        # すでに動いていれば終了する
        if ffmpeg_proc:
            print("Stopping previous FFmpeg process...")
            ffmpeg_proc.terminate()
            try:
                ffmpeg_proc.wait(timeout=3)
            except Exception:
                ffmpeg_proc.kill()
            print("Previous FFmpeg process stopped.")

        print("Starting FFmpeg HLS encoding...")
        # 既存セグメントのクリーンアップ
        for f in os.listdir(HLS_DIR):
            if f.endswith(".ts") or f.endswith(".m3u8"):
                try:
                    os.remove(os.path.join(HLS_DIR, f))
                except Exception:
                    pass

        cmd = [
            "ffmpeg",
            "-re",
            "-i", video_url
        ]
        if audio_url:
            cmd.extend(["-i", audio_url])
            
        cmd.extend(["-map", "0:v:0"])
        if audio_url:
            cmd.extend(["-map", "1:a:0"])
        else:
            cmd.extend(["-map", "0:a:0?"])

        cmd.extend([
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "128k",
            "-f", "hls",
            "-hls_time", "2",
            "-hls_list_size", "5",
            "-hls_flags", "delete_segments",
            "-hls_segment_filename", os.path.join(HLS_DIR, "seg_%03d.ts"),
            os.path.join(HLS_DIR, "stream.m3u8")
        ])
        
        ffmpeg_proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, encoding="utf-8")
        threading.Thread(target=log_stream, args=(ffmpeg_proc.stderr, "ffmpeg"), daemon=True).start()
        print("FFmpeg started successfully.")

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
            
    threading.Thread(target=log_stream, args=(process.stderr, "tunnel"), daemon=True).start()
    return process, tunnel_url

if __name__ == "__main__":
    initial_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    
    # 1. サーバー起動
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    time.sleep(1)
    
    # 2. トンネル起動
    tunnel_proc, tunnel_url = start_tunnel()
    if not tunnel_url:
        print("Failed to start tunnel.")
        sys.exit(1)
        
    # 3. 初期ストリーム起動
    try:
        v_url, a_url, title = get_stream_urls(initial_url)
        print(f"Playing Title: {title}")
        start_ffmpeg(v_url, a_url)
    except Exception as e:
        print(f"Failed to start initial stream: {e}")
        
    print("\n--- Control Panel ---")
    print("Paste a new YouTube URL and press Enter to switch the video stream.")
    print("Type 'exit' to quit.\n")
    
    while True:
        try:
            inp = input("New URL (or 'exit'): ")
            if inp.strip().lower() == "exit":
                break
            if not inp.strip():
                continue
                
            new_url = inp.strip()
            print(f"Switching stream to: {new_url}")
            try:
                v_url, a_url, title = get_stream_urls(new_url)
                print(f"Next Title: {title}")
                start_ffmpeg(v_url, a_url)
                print("Switch complete. Check VRChat player behavior.")
            except Exception as e:
                print(f"Failed to switch stream: {e}")
                
        except KeyboardInterrupt:
            break
            
    print("Stopping all processes...")
    with ffmpeg_lock:
        if ffmpeg_proc:
            ffmpeg_proc.terminate()
    tunnel_proc.terminate()
    print("Done.")
