$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not (Test-Path -LiteralPath '.\data\dictionary.sqlite3')) {
    & '.\.venv\Scripts\python.exe' '.\scripts\build_dictionary.py'
    if ($LASTEXITCODE -ne 0) { throw 'Dictionary build failed' }
}
& '.\.venv\Scripts\python.exe' -m PyInstaller --noconfirm --clean --windowed --onedir --name LocalTranslate --add-data 'data/dictionary.sqlite3;data' --add-data 'data/ECDICT-LICENSE.txt;data' --collect-all ctranslate2 --collect-all tokenizers --exclude-module transformers --exclude-module torch --exclude-module tensorflow --exclude-module matplotlib --exclude-module scipy main.py
if ($LASTEXITCODE -ne 0) { throw 'Build failed' }
Copy-Item -LiteralPath '.\README.md' -Destination '.\dist\LocalTranslate\使用说明.md'
Write-Host 'Ready: dist\LocalTranslate\LocalTranslate.exe'
