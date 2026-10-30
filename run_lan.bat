@echo off
title PulseCheck (device mode)
cd /d "%~dp0"
where python >nul 2>nul && (set PY=python) || (set PY=py)
echo Installing what PulseCheck needs (first run only)...
%PY% -m pip install -q -r webapp\requirements.txt
if errorlevel 1 (echo. & echo Could not install the packages. Check your internet connection. & pause & exit /b 1)
set PULSECHECK_HOST=0.0.0.0
set PULSECHECK_PORT=8000
echo.
echo If Windows asks about the firewall, choose "Allow access" (private networks).
%PY% -m webapp.run
pause
