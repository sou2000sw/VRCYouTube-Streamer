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

# 配信プロセス管理用
hls_proc = None
send_proc = None
relay_active = False
current_stdin = None

# ロック
process_lock = threading.Lock()

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
                if "Error" in line or "warning" in line or "Output" in line:
                    print(f"[{label}] {line.strip()}", flush=True)
    except Exception:
        pass

def start_hls_output_process():
    global hls_proc, current_stdin
    # 既存セグメントのクリーンアップ
    for f in os.listdir(HLS_DIR):
        if f.endswith(".ts") or f.endswith(".m3u8"):
            try:
                os.remove(os.path.join(HLS_DIR, f))
            except Exception:
                pass

    print("Starting HLS Output FFmpeg (Receiver)...")
    # pipe:0 から MPEG-TS を読み込み、HLSとして配信する
    # 映像は再エンコードせずコピー、音声もコピー（トランスコード負荷ゼロ）
    cmd = [
        "ffmpeg",
        "-y",
        "-i", "pipe:0",
        "-c:v", "copy",
        "-c:a", "copy",
        "-f", "hls",
        "-hls_time", "4",              # 4秒に変更してリクエスト負荷と遅延の影響を低減
        "-hls_list_size", "6",         # バッファ保持数を少し増やす
        "-hls_flags", "delete_segments",
        "-hls_segment_filename", os.path.join(HLS_DIR, "seg_%03d.ts"),
        os.path.join(HLS_DIR, "stream.m3u8")
    ]
    
    hls_proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8"
    )
    current_stdin = hls_proc.stdin
    # エラーログ監視用スレッド
    threading.Thread(target=log_stream, args=(hls_proc.stderr, "ffmpeg-hls"), daemon=True).start()
    print("HLS Receiver started.")

def relay_stream_data(proc_to_read, stdin_to_write):
    global relay_active
    relay_active = True
    print("[Relay] Stream data relay started.")
    try:
        while relay_active:
            # 16KB ずつバイナリで読み込んで流し込む
            data = proc_to_read.stdout.read(16384)
            if not data:
                break
            stdin_to_write.write(data)
            stdin_to_write.flush()
    except Exception as e:
        print(f"[Relay] Error during relay: {e}")
    finally:
        print("[Relay] Stream data relay stopped.")
        relay_active = False

def play_video(youtube_url):
    global send_proc, relay_active
    
    # 1. YouTube URL解析
    try:
        video_url, audio_url, title = get_stream_urls(youtube_url)
        print(f"\nNext Title to Play: {title}")
    except Exception as e:
        print(f"Failed to analyze URL: {e}")
        return False

    with process_lock:
        # 2. 既存の送信プロセスがあれば停止
        if send_proc:
            print("Stopping current stream sender...")
            relay_active = False # リレーを一時停止
            send_proc.terminate()
            try:
                send_proc.wait(timeout=3)
            except Exception:
                send_proc.kill()
            print("Current stream sender stopped.")

        # 3. 新しい送信プロセスを起動
        print("Starting stream sender (FFmpeg -> MPEG-TS)...")
        cmd = [
            "ffmpeg",
            "-re",
            "-fflags", "+genpts", # タイムスタンプ再生成
            "-i", video_url
        ]
        if audio_url:
            cmd.extend(["-i", audio_url])
            
        cmd.extend(["-map", "0:v:0"])
        if audio_url:
            cmd.extend(["-map", "1:a:0"])
        else:
            cmd.extend(["-map", "0:a:0?"])

        # 送信側でmpegtsコンテナ（映像コピー、音声はVRChatの互換性のために念のためAACに変換。負荷極小）
        # aresample=async=1 を追加して、映像と音声のタイムスタンプズレを同期させる
        cmd.extend([
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "128k",
            "-af", "aresample=async=1",
            "-f", "mpegts",
            "pipe:1"
        ])
        
        send_proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0 # バッファリングなし
        )
        
        # エラーログ監視用
        # バイナリモードなのでデコーダ側のstderrはテキスト変換して読み取る必要がある
        # 簡易的に別の監視スレッドを立ち上げる
        def log_stderr_binary(proc):
            try:
                for line in proc.stderr:
                    l = line.decode('utf-8', errors='ignore').strip()
                    if "Error" in l or "warning" in l or "Output" in l:
                        print(f"[ffmpeg-send] {l}", flush=True)
            except Exception:
                pass
        threading.Thread(target=log_stderr_binary, args=(send_proc,), daemon=True).start()

        # 4. リレースレッドの起動
        # 送信プロセスの stdout (バイナリ) から読み込み、HLSプロセスの stdin (バイナリ) に書き込む
        # current_stdin のバイナリ書き込み口は current_stdin.buffer
        threading.Thread(
            target=relay_stream_data, 
            args=(send_proc, current_stdin.buffer), 
            daemon=True
        ).start()
        print("Switch complete.")
        return True

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
        
    # 3. 受信側（HLS出力）プロセス起動
    start_hls_output_process()
    
    # 4. 初期動画再生開始
    play_video(initial_url)
    
    print("\n--- Control Panel (Pipe Relay Mode) ---")
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
            play_video(new_url)
                
        except KeyboardInterrupt:
            break
            
    print("Stopping all processes...")
    relay_active = False
    with process_lock:
        if send_proc:
            send_proc.terminate()
        if hls_proc:
            hls_proc.terminate()
    tunnel_proc.terminate()
    print("Done.")
