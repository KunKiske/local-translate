@echo off
setlocal
cd /d "%~dp0"
title LocalTranslate - First Run
echo LocalTranslate first-run setup
echo This will install missing Python, dependencies and the offline dictionary.
echo Internet access is required. Models are NOT downloaded.
echo Existing model paths, hotkeys and preferences will be preserved.
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1" -InstallPython
if errorlevel 1 (
    echo.
    echo Setup failed. See the error above and install.log in this folder.
    echo Fix the problem and run this BAT again.
    pause
    exit /b 1
)
echo.
echo Setup complete. Opening LocalTranslate settings; choose your local model.
start "" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0main.py" --settings
if errorlevel 1 (
    echo Could not start LocalTranslate. Run diagnose.cmd to see the error.
    pause
    exit /b 1
)
echo Next time, use the VBS launcher in this folder.
pause
