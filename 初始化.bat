@echo off
setlocal
cd /d "%~dp0"

echo.
echo Novel Writer Agent Init
echo ==========================
echo.

set "PYTHON=.venv\Scripts\python.exe"
set "SYSTEM_PYTHON="
set "NEED_INSTALL=0"

where python >nul 2>nul
if not errorlevel 1 set "SYSTEM_PYTHON=python"

if not defined SYSTEM_PYTHON (
  where py >nul 2>nul
  if not errorlevel 1 set "SYSTEM_PYTHON=py -3"
)

if not exist "%PYTHON%" (
  if not defined SYSTEM_PYTHON (
    echo Python was not found.
    echo Please install Python 3.10 or later and enable "Add python.exe to PATH".
    echo Download: https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
  )
  echo Creating virtual environment .venv ...
  %SYSTEM_PYTHON% -m venv .venv
  if errorlevel 1 (
    echo Failed to create virtual environment. Please check your Python installation.
    echo.
    pause
    exit /b 1
  )
  set "NEED_INSTALL=1"
)

"%PYTHON%" --version >nul 2>nul
if errorlevel 1 (
  if not defined SYSTEM_PYTHON (
    echo Current .venv is not usable and system Python was not found.
    echo.
    pause
    exit /b 1
  )
  echo Current .venv is not usable. Recreating virtual environment ...
  rmdir /s /q ".venv"
  %SYSTEM_PYTHON% -m venv .venv
  if errorlevel 1 (
    echo Failed to recreate virtual environment. Please check your Python installation.
    echo.
    pause
    exit /b 1
  )
  set "NEED_INSTALL=1"
)

if "%NEED_INSTALL%"=="1" (
  echo.
  echo Installing/checking dependencies ...
  "%PYTHON%" -m pip install -r requirements.txt
  if errorlevel 1 (
    echo Failed to install dependencies. Please check network connection or requirements.txt.
    echo.
    pause
    exit /b 1
  )
)

echo.
"%PYTHON%" "%~dp0scripts\init_env.py"
echo.
pause
