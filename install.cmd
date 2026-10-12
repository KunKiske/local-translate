@echo off
cd /d "%~dp0"
echo Preparing LocalTranslate source installation...
echo Internet access and Python 3.10-3.13 x64 are required.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1"
if errorlevel 1 (
    echo Installation failed. See the error above.
    pause
    exit /b 1
)
echo Installation complete. Run the VBS launcher, then choose your model folder.
pause
