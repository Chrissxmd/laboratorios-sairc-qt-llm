@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Primero ejecuta INSTALAR.bat.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" main_qt.py
if errorlevel 1 pause
