import os
import sys
import io
import argparse
import subprocess
import shutil
import zipfile

if sys.platform == "win32" and sys.stdout is not None:
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    except Exception:
        pass

APP_VERSION = "2.5.0"

def generate_startup_shortcuts(target_dir):
    """指定ディレクトリに各種起動用バッチファイルを作成"""
    os.makedirs(target_dir, exist_ok=True)
    
    # 1. ローカルテスト起動バッチ (トンネルなし)
    bat_local = os.path.join(target_dir, "VRCYouTubeStreamer (Local Test).bat")
    with open(bat_local, "w", encoding="cp932", errors="replace") as f:
        f.write('@echo off\r\n'
                'echo ======================================================\r\n'
                'echo Starting VRCYouTube Streamer in Local Test Mode\r\n'
                'echo (Cloudflare Tunnel: DISABLED)\r\n'
                'echo Local URL: http://localhost:8000\r\n'
                'echo ======================================================\r\n'
                'start "" "%~dp0VRCYouTubeStreamer.exe" --no-tunnel\r\n')
    print(f"Created startup shortcut: {bat_local}", flush=True)

    # 2. 通常起動バッチ (トンネルあり)
    bat_normal = os.path.join(target_dir, "VRCYouTubeStreamer (Normal).bat")
    with open(bat_normal, "w", encoding="cp932", errors="replace") as f:
        f.write('@echo off\r\n'
                'echo ======================================================\r\n'
                'echo Starting VRCYouTube Streamer in Normal Mode\r\n'
                'echo (Cloudflare Tunnel: ENABLED)\r\n'
                'echo ======================================================\r\n'
                'start "" "%~dp0VRCYouTubeStreamer.exe" --tunnel\r\n')
    print(f"Created startup shortcut: {bat_normal}", flush=True)

    # 3. ヘッドレスローカル起動バッチ
    bat_headless = os.path.join(target_dir, "VRCYouTubeStreamer (Headless Test).bat")
    with open(bat_headless, "w", encoding="cp932", errors="replace") as f:
        f.write('@echo off\r\n'
                'echo ======================================================\r\n'
                'echo Starting VRCYouTube Streamer in Headless Local Mode\r\n'
                'echo (Cloudflare Tunnel: DISABLED, GUI: DISABLED)\r\n'
                'echo ======================================================\r\n'
                '"%~dp0VRCYouTubeStreamer.exe" --headless --no-tunnel\r\n'
                'pause\r\n')
    print(f"Created startup shortcut: {bat_headless}", flush=True)

def generate_root_shortcuts():
    """プロジェクトルート用のPython直接起動ショートカット"""
    bat_root_local = os.path.abspath("Start_LocalTest.bat")
    with open(bat_root_local, "w", encoding="cp932", errors="replace") as f:
        f.write('@echo off\r\n'
                'cd /d "%~dp0"\r\n'
                'echo Starting VRCYouTube Streamer in Local Test Mode (No Tunnel)...\r\n'
                'python gui_streamer.py --no-tunnel\r\n'
                'pause\r\n')

    bat_root_normal = os.path.abspath("Start_Normal.bat")
    with open(bat_root_normal, "w", encoding="cp932", errors="replace") as f:
        f.write('@echo off\r\n'
                'cd /d "%~dp0"\r\n'
                'echo Starting VRCYouTube Streamer (Normal Mode - Tunnel Enabled)...\r\n'
                'python gui_streamer.py --tunnel\r\n'
                'pause\r\n')

def get_ffmpeg_source():
    """ローカルまたはPATH内のffmpeg.exeパスを取得"""
    local_ffmpeg = os.path.abspath("ffmpeg.exe")
    if os.path.exists(local_ffmpeg):
        return local_ffmpeg
    dist_ffmpeg = os.path.abspath("dist/ffmpeg.exe")
    if os.path.exists(dist_ffmpeg):
        return dist_ffmpeg
    ffmpeg_path = shutil.which("ffmpeg")
    if ffmpeg_path:
        if sys.platform == "win32" and not ffmpeg_path.lower().endswith(".exe"):
            ffmpeg_path_exe = ffmpeg_path + ".exe"
            if os.path.exists(ffmpeg_path_exe):
                return ffmpeg_path_exe
        if os.path.exists(ffmpeg_path):
            return ffmpeg_path
    return None

def package_plugin(version=APP_VERSION):
    """plugin/ フォルダの資材を整理し、VRCBeacon用プラグインZIPパッケージを生成"""
    plugin_root = os.path.abspath("plugin")
    plugin_bin = os.path.join(plugin_root, "bin")
    releases_root = os.path.abspath("releases")
    os.makedirs(plugin_bin, exist_ok=True)
    os.makedirs(releases_root, exist_ok=True)

    print(f"\n==================================================", flush=True)
    print(f"Packaging VRCBeacon Plugin for v{version}...", flush=True)
    print(f"==================================================", flush=True)

    # 1. dist/ から plugin/bin/ へバイナリを同期
    src_exe = os.path.abspath("dist/VRCYouTubeStreamer.exe")
    if os.path.exists(src_exe):
        shutil.copy2(src_exe, os.path.join(plugin_bin, "VRCYouTubeStreamer.exe"))
        print("[OK] Copied VRCYouTubeStreamer.exe -> plugin/bin/", flush=True)

    ffmpeg_src = get_ffmpeg_source()
    if ffmpeg_src and os.path.exists(ffmpeg_src):
        shutil.copy2(ffmpeg_src, os.path.join(plugin_bin, "ffmpeg.exe"))
        print(f"[OK] Copied ffmpeg.exe -> plugin/bin/", flush=True)

    src_config = os.path.abspath("config.json")
    if os.path.exists(src_config):
        shutil.copy2(src_config, os.path.join(plugin_bin, "config.json"))
        print("[OK] Copied config.json -> plugin/bin/", flush=True)

    # 2. プラグインZIPアーカイブ作成
    zip_path = os.path.join(releases_root, f"vrcbeacon-plugin-vrcyoutube-v{version}.zip")
    print(f"Creating Plugin ZIP archive: {zip_path} ...", flush=True)
    try:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(plugin_root):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, plugin_root)
                    zf.write(file_path, arcname)
        print(f"[OK] Successfully generated Plugin ZIP: {zip_path}", flush=True)
    except Exception as e:
        print(f"[WARN] Failed to create Plugin ZIP: {e}", flush=True)

def create_versioned_release(version=APP_VERSION):
    """releases/VRCYouTubeStreamer_v{version}/ 配布用パッケージおよび ZIP を生成"""
    release_dir_name = f"VRCYouTubeStreamer_v{version}"
    releases_root = os.path.abspath("releases")
    target_dir = os.path.join(releases_root, release_dir_name)
    os.makedirs(target_dir, exist_ok=True)

    print(f"\n==================================================", flush=True)
    print(f"Creating Release Package for v{version}...", flush=True)
    print(f"Target Directory: {target_dir}", flush=True)
    print(f"==================================================", flush=True)

    # 1. EXE のコピー
    src_exe = os.path.abspath("dist/VRCYouTubeStreamer.exe")
    if os.path.exists(src_exe):
        shutil.copy2(src_exe, os.path.join(target_dir, "VRCYouTubeStreamer.exe"))
        print("[OK] Copied VRCYouTubeStreamer.exe", flush=True)
    else:
        print("[WARN] dist/VRCYouTubeStreamer.exe not found!", flush=True)

    # 2. ffmpeg.exe のコピー
    ffmpeg_src = get_ffmpeg_source()
    if ffmpeg_src and os.path.exists(ffmpeg_src):
        shutil.copy2(ffmpeg_src, os.path.join(target_dir, "ffmpeg.exe"))
        print(f"[OK] Copied ffmpeg.exe from {ffmpeg_src}", flush=True)
    else:
        print("[WARN] ffmpeg.exe was not found to package.", flush=True)

    # 3. config.json のコピー
    src_config = os.path.abspath("config.json")
    if os.path.exists(src_config):
        shutil.copy2(src_config, os.path.join(target_dir, "config.json"))
        print("[OK] Copied config.json", flush=True)

    # 4. ドキュメント類のコピー
    for doc in ["dist/README.txt", "dist/FFmpeg_LICENSE.txt", "CHANGELOG.md", "README.md"]:
        if os.path.exists(doc):
            dest_name = os.path.basename(doc)
            shutil.copy2(doc, os.path.join(target_dir, dest_name))
            print(f"[OK] Copied {dest_name}", flush=True)

    # 5. 各種起動用バッチファイルの生成
    generate_startup_shortcuts(target_dir)

    # 6. ZIP アーカイブの生成
    zip_path = os.path.join(releases_root, f"{release_dir_name}.zip")
    print(f"Creating ZIP archive: {zip_path} ...", flush=True)
    try:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(target_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, releases_root)
                    zf.write(file_path, arcname)
        print(f"[OK] Successfully generated ZIP: {zip_path}", flush=True)
    except Exception as e:
        print(f"[WARN] Failed to create ZIP archive: {e}", flush=True)

    # 7. プラグインパッケージの作成
    package_plugin(version)

    print(f"\n==================================================", flush=True)
    print(f"Release v{version} package created successfully!", flush=True)
    print(f"Folder: {target_dir}")
    print(f"Zip:    {zip_path}")
    print(f"==================================================\n", flush=True)

def build(version=APP_VERSION):
    print(f"Starting PyInstaller build process for v{version}...", flush=True)
    
    try:
        import PyInstaller
        print(f"PyInstaller is already installed (version: {PyInstaller.__version__})", flush=True)
    except ImportError:
        print("PyInstaller is not installed. Installing it via pip...", flush=True)
        try:
            subprocess.run([sys.executable, "-m", "pip", "install", "pyinstaller"], check=True)
            print("Successfully installed PyInstaller.", flush=True)
        except Exception as e:
            print(f"Failed to install PyInstaller: {e}", flush=True)
            sys.exit(1)
        
    cmd = [
        "pyinstaller",
        "--onefile",
        "--noconsole",
        "--name", "VRCYouTubeStreamer",
        "--add-data", "cloudflared.exe;.",
        "--collect-all", "customtkinter",
        "--collect-all", "qrcode",
        "--collect-all", "PIL",
        "--clean",
        "gui_streamer.py"
    ]
    
    print(f"Running command: {' '.join(cmd)}", flush=True)
    try:
        subprocess.run(cmd, check=True)
    except FileNotFoundError:
        print("pyinstaller command not found in PATH. Retrying with python -m PyInstaller...", flush=True)
        cmd[0:1] = [sys.executable, "-m", "PyInstaller"]
        print(f"Running command: {' '.join(cmd)}", flush=True)
        subprocess.run(cmd, check=True)

    # dist フォルダの更新
    generate_startup_shortcuts(os.path.abspath("dist"))
    generate_root_shortcuts()
    ffmpeg_src = get_ffmpeg_source()
    if ffmpeg_src and os.path.exists(ffmpeg_src):
        try:
            shutil.copy2(ffmpeg_src, os.path.abspath("dist/ffmpeg.exe"))
        except Exception:
            pass

    # バージョン別配布用パッケージ (releases/VRCYouTubeStreamer_v<version>/) の生成
    create_versioned_release(version)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build and Package VRCYouTubeStreamer")
    parser.add_argument("--version", "-v", type=str, default=APP_VERSION, help=f"Release version string (default: {APP_VERSION})")
    parser.add_argument("--package-only", action="store_true", help="Skip PyInstaller build and only package existing dist/ files")
    parser.add_argument("--plugin-only", action="store_true", help="Package only the VRCBeacon plugin")
    args = parser.parse_args()

    if args.plugin_only:
        package_plugin(args.version)
    elif args.package_only:
        create_versioned_release(args.version)
    else:
        build(args.version)
