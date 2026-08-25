@echo off
echo ======================================================
echo Starting VRCYouTube Streamer in Normal Mode
echo (Cloudflare Tunnel: ENABLED)
echo ======================================================
start "" "%~dp0VRCYouTubeStreamer.exe" --tunnel
