@echo off
cd /d "%~dp0"
echo Starting VRCYouTube Streamer in Local Test Mode (No Tunnel)...
python gui_streamer.py --no-tunnel
pause
