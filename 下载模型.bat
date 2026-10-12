@echo off
setlocal DisableDelayedExpansion
cd /d "%~dp0"
title LocalTranslate - Download NLLB-600M
echo Download NLLB-600M ^(CTranslate2 INT8, about 617 MiB^).
echo Source: huggingface.co / JustFrederik
echo Destination: "%~dp0models\NLLB-600M"
echo Model license: CC-BY-NC-4.0. See the downloaded README.md.
echo Existing models and application settings will be preserved.
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\download_model.ps1"
if errorlevel 1 (
    echo.
    echo Download failed. See the error above or download-model.log.
    echo Check your connection to huggingface.co and run this BAT again to resume.
    pause
    exit /b 1
)
echo.
echo Model ready. Select the folder shown above in LocalTranslate settings.
echo For first-time application setup, use the first-run BAT in this folder.
pause
