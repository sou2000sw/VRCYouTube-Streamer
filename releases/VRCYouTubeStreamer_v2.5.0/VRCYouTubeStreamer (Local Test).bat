@echo off
echo ======================================================
echo Starting VRCYouTube Streamer in Local Test Mode
echo (Cloudflare Tunnel: DISABLED)
echo Local URL: http://localhost:8000
echo ======================================================
start "" "%~dp0VRCYouTubeStreamer.exe" --no-tunnel
