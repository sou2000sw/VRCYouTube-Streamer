@echo off
echo ======================================================
echo Starting VRCYouTube Streamer in Headless Local Mode
echo (Cloudflare Tunnel: DISABLED, GUI: DISABLED)
echo ======================================================
"%~dp0VRCYouTubeStreamer.exe" --headless --no-tunnel
pause
