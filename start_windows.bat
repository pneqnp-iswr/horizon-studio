@echo off
cd /d "%~dp0"
where py >nul 2>nul
if %ERRORLEVEL%==0 (
    start "Horizon Studio" cmd /k "py -3 studio.py"
) else (
    start "Horizon Studio" cmd /k "python studio.py"
)
timeout /t 2 /nobreak >nul
start "" "http://127.0.0.1:8787"
