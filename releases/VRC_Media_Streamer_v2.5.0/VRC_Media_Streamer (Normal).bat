@echo off
echo ======================================================
echo Starting VRC_Media_Streamer in Normal Mode
echo (Cloudflare Tunnel: ENABLED)
echo ======================================================
start "" "%~dp0VRC_Media_Streamer.exe" --tunnel
