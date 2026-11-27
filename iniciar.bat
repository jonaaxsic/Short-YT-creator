@echo off
cd /d %~dp0

rem Evita que un clic dentro de la consola la congele (modo Seleccionar).
reg add "HKCU\Console" /v QuickEdit /t REG_DWORD /d 0 /f >nul 2>&1

if not exist .venv\Scripts\python.exe (
  echo Preparando entorno por primera vez...
  python -m venv .venv
  .venv\Scripts\python.exe -m pip install -q -r requirements.txt
)

rem Cierra una instancia anterior para arrancar siempre limpio.
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8502" ^| findstr "LISTENING"') do (
  taskkill /F /PID %%a >nul 2>&1
)

start "ShortsServer" .venv\Scripts\python.exe -m app 8502

rem Espera a que el servidor responda antes de abrir el navegador.
set /a intentos=0
:esperar
powershell -NoProfile -Command "try { (Invoke-WebRequest -UseBasicParsing 'http://127.0.0.1:8502/api/state' -TimeoutSec 2).StatusCode } catch { exit 1 }" >nul 2>&1
if not errorlevel 1 goto abrir
set /a intentos+=1
if %intentos% LSS 30 (
  timeout /t 1 >nul
  goto esperar
)

:abrir
start "" http://localhost:8502
