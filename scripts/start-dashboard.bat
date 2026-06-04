@echo off
cd /d "%~dp0..\frontend"
echo Dashboard: http://localhost:8000
echo Ctrl+C para detener.
python -m http.server 8000
pause
