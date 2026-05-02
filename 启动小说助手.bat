@echo off
setlocal
cd /d "%~dp0"

set "HOST=127.0.0.1"
set "PORT=8000"
set "URL=http://%HOST%:%PORT%"
set "OPEN_URL=%URL%/?t=%RANDOM%"
set "HEALTH_URL=%URL%/api/health"

set "PYTHON=.venv\Scripts\python.exe"

if not exist "%PYTHON%" (
  echo Virtual environment was not found.
  echo Please run the init bat file first.
  echo.
  pause
  exit /b 1
)

"%PYTHON%" --version >nul 2>nul
if errorlevel 1 (
  echo Current virtual environment is not usable.
  echo It may be broken after moving or packaging this project.
  echo Please run the init bat file again.
  echo.
  pause
  exit /b 1
)

echo Starting Novel Writer Agent...
echo Waiting for server, then opening: %URL%
start "" /min powershell -NoProfile -ExecutionPolicy Bypass -Command "$health='%HEALTH_URL%'; $open='%OPEN_URL%'; for ($i = 0; $i -lt 60; $i++) { try { Invoke-WebRequest -Uri $health -UseBasicParsing -TimeoutSec 1 | Out-Null; Start-Process $open; exit 0 } catch { Start-Sleep -Seconds 1 } }"
"%PYTHON%" -m uvicorn app.api:app --host %HOST% --port %PORT% --no-use-colors

echo.
echo Server stopped.
pause
