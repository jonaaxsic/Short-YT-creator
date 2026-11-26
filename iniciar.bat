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

start "" http://localhost:8502
start "ShortsServer" .venv\Scripts\python.exe -m app 8502
