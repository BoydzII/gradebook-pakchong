@echo off
chcp 65001 >nul
title KruSpace Voice Studio - close this window to stop
cd /d "%~dp0..\.."
python tools\voice_studio\studio.py
if errorlevel 1 pause
