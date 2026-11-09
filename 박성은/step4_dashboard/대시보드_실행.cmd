@echo off
chcp 65001 >nul
cd /d "%~dp0"
set MARIMO_SKIP_UPDATE_CHECK=1
uv run python -m marimo run app.py
pause
