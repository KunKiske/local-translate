@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Python environment is missing. Run install.cmd first.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" scripts\check_runtime.py --dependencies
if errorlevel 1 (
    echo Dependency check failed. Run install.cmd to repair the environment.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" main.py
if errorlevel 1 echo Startup failed. Copy the error above when reporting this problem.
pause
