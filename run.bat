@echo off
rem Lightning launcher for Windows: double-click to start.
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo First run: setting up Lightning...
  py -3 -m venv .venv 2>nul || python -m venv .venv
  if errorlevel 1 (
    echo Python 3.11+ is needed. Install it from https://www.python.org/downloads/ and tick "Add python.exe to PATH".
    pause
    exit /b 1
  )
)
.venv\Scripts\python.exe tools\install_source.py
.venv\Scripts\python.exe -m lightning %*
pause
