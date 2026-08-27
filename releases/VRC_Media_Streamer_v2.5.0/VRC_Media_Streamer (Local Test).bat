@echo off
echo ======================================================
echo Starting VRC_Media_Streamer in Local Test Mode
echo (Cloudflare Tunnel: DISABLED)
echo Local URL: http://localhost:8000
echo ======================================================
start "" "%~dp0VRC_Media_Streamer.exe" --no-tunnel
