@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    py -3.11 -m venv .venv
    if errorlevel 1 goto error
)
".venv\Scripts\python.exe" -m pip install -r requirements.txt -c requirements-lock.txt
if errorlevel 1 goto error
echo Instalacion terminada. Ejecuta INICIAR.bat.
pause
exit /b 0
:error
echo Instalacion incompleta. Verifica Python 3.11 y la conexion a Internet.
pause
exit /b 1
