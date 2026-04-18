@echo off
setlocal
cd /d "%~dp0"

set "LAUNCHER=%~dp0start_agentrewind.py"
set "PYTHON_CMD="

if exist "%~dp0backend\.venv\Scripts\python.exe" (
  "%~dp0backend\.venv\Scripts\python.exe" --version >nul 2>nul
  if not errorlevel 1 (
    set "PYTHON_CMD=%~dp0backend\.venv\Scripts\python.exe"
  )
)

if not defined PYTHON_CMD (
  python --version >nul 2>nul
  if not errorlevel 1 (
    set "PYTHON_CMD=python"
  )
)

if not defined PYTHON_CMD (
  py -3 --version >nul 2>nul
  if not errorlevel 1 (
    set "PYTHON_CMD=py -3"
  )
)

if not defined PYTHON_CMD (
  echo Python 3.11+ was not found. Install Python and run agentrewind.bat again.
  exit /b 1
)

call %PYTHON_CMD% "%LAUNCHER%" %*
exit /b %errorlevel%
