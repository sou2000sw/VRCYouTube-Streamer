import os
import sys
import subprocess
import shutil

def copy_ffmpeg_to_dist():
    ffmpeg_path = shutil.which("ffmpeg")
    if ffmpeg_path:
        # Windows向けに .exe 拡張子の補正
        if sys.platform == "win32" and not ffmpeg_path.lower().endswith(".exe"):
            ffmpeg_path_exe = ffmpeg_path + ".exe"
            if os.path.exists(ffmpeg_path_exe):
                ffmpeg_path = ffmpeg_path_exe
        
        if os.path.exists(ffmpeg_path):
            dest = os.path.abspath("dist/ffmpeg.exe")
            print(f"Found ffmpeg at {ffmpeg_path}. Copying to dist/...", flush=True)
            try:
                shutil.copy2(ffmpeg_path, dest)
                print(f"Successfully copied ffmpeg to {dest}", flush=True)
            except Exception as e:
                print(f"Failed to copy ffmpeg: {e}", flush=True)
        else:
            print(f"ffmpeg path found at {ffmpeg_path} but cannot resolve file.", flush=True)
    else:
        print("\n[WARNING] ffmpeg was not found in system PATH.", flush=True)
        print("Please manually place 'ffmpeg.exe' into the 'dist' directory for portable distribution.\n", flush=True)

def build():
    print("Starting PyInstaller build process...", flush=True)
    
    # PyInstaller がインストールされているかチェックし、なければインストールする
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
        copy_ffmpeg_to_dist()
        print("\n==================================================", flush=True)
        print("Build completed successfully!", flush=True)
        print("The executable and portable files are in 'dist' directory:")
        print(f"  {os.path.abspath('dist/VRCYouTubeStreamer.exe')}")
        print(f"  {os.path.abspath('dist/ffmpeg.exe')} (if copied)")
        print("==================================================\n", flush=True)
    except subprocess.CalledProcessError as e:
        print(f"\nBuild failed with exit code: {e.returncode}", flush=True)
        sys.exit(e.returncode)
    except FileNotFoundError:
        # PATHにpyinstallerがない場合、python -m PyInstaller で再試行
        print("pyinstaller command not found in PATH. Retrying with python -m PyInstaller...", flush=True)
        cmd[0:1] = [sys.executable, "-m", "PyInstaller"]
        print(f"Running command: {' '.join(cmd)}", flush=True)
        try:
            subprocess.run(cmd, check=True)
            copy_ffmpeg_to_dist()
            print("\n==================================================", flush=True)
            print("Build completed successfully!", flush=True)
            print("The executable and portable files are in 'dist' directory:")
            print(f"  {os.path.abspath('dist/VRCYouTubeStreamer.exe')}")
            print(f"  {os.path.abspath('dist/ffmpeg.exe')} (if copied)")
            print("==================================================\n", flush=True)
        except Exception as e2:
            print(f"Retry build failed: {e2}", flush=True)
            sys.exit(1)

if __name__ == "__main__":
    build()
