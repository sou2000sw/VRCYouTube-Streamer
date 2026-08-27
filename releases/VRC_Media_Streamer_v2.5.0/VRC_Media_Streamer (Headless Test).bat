@echo off
echo ======================================================
echo Starting VRC_Media_Streamer in Headless Local Mode
echo (Cloudflare Tunnel: DISABLED, GUI: DISABLED)
echo ======================================================
"%~dp0VRC_Media_Streamer.exe" --headless --no-tunnel
pause
