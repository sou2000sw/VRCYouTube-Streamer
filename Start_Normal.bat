@echo off
cd /d "%~dp0"
echo Starting VRCYouTube Streamer (Normal Mode - Tunnel Enabled)...
python gui_streamer.py --tunnel
pause
