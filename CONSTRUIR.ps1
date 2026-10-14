$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$migrationPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $migrationPython)) { throw 'Ejecuta INSTALAR.bat primero.' }
& $migrationPython -m pip install -r requirements-build.txt
if ($LASTEXITCODE -ne 0) { throw 'No se pudieron instalar las herramientas de empaquetado.' }
& $migrationPython -m PyInstaller --noconfirm --distpath dist/10.0.7 AuditoriaSAIRC.spec
if ($LASTEXITCODE -ne 0) { throw 'No se pudo generar el ejecutable.' }
Write-Host 'Ejecutable actualizado: dist\10.0.7\AuditoriaSAIRC.exe'
