@echo off
title PulseCheck
cd /d "%~dp0"
where python >nul 2>nul && (set PY=python) || (set PY=py)
echo Installing what PulseCheck needs (first run only)...
%PY% -m pip install -q -r webapp\requirements.txt
if errorlevel 1 (echo. & echo Could not install the packages. Check your internet connection. & pause & exit /b 1)
%PY% -m webapp.run
pause
