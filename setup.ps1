$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$taskTranscript = Join-Path $PSScriptRoot 'install.log'
Start-Transcript -Path $taskTranscript -Force | Out-Null
try {
    if (-not (Test-Path -LiteralPath '.\.venv\Scripts\python.exe')) {
        $taskPython = $null
        $taskArguments = @()
        if (Get-Command py -ErrorAction SilentlyContinue) {
            & py -3.11 '.\scripts\check_runtime.py'
            if ($LASTEXITCODE -eq 0) { $taskPython = 'py'; $taskArguments = @('-3.11') }
        }
        if (-not $taskPython -and (Get-Command python -ErrorAction SilentlyContinue)) {
            & python '.\scripts\check_runtime.py'
            if ($LASTEXITCODE -eq 0) { $taskPython = 'python' }
        }
        if (-not $taskPython) {
            throw 'Python 3.11 x64 was not found. Install it from https://www.python.org/downloads/windows/ (enable the Python launcher), then run install.cmd again. The portable ZIP does not require Python.'
        }
        & $taskPython @taskArguments -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw 'Could not create .venv. Check the error above and folder write permissions.' }
    }
    & '.\.venv\Scripts\python.exe' '.\scripts\check_runtime.py'
    if ($LASTEXITCODE -ne 0) { throw 'The .venv environment is incompatible or was copied from another PC. Rename .venv to .venv-old, then run install.cmd again.' }
    & '.\.venv\Scripts\python.exe' -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed. Check the network connection and the pip error above.' }
    & '.\.venv\Scripts\python.exe' '.\scripts\check_runtime.py' --dependencies
    if ($LASTEXITCODE -ne 0) { throw 'Dependency/DLL check failed. See the traceback above or install.log.' }
    if (-not (Test-Path -LiteralPath '.\data\dictionary.sqlite3')) {
        & '.\.venv\Scripts\python.exe' '.\scripts\build_dictionary.py'
        if ($LASTEXITCODE -ne 0) { throw 'Dictionary preparation failed. Check the network connection and retry install.cmd.' }
    }
    Write-Host 'Ready. Double-click the VBS launcher. Select a local CTranslate2 model in Settings.'
} catch {
    Write-Host ('INSTALL FAILED: ' + $_.Exception.Message) -ForegroundColor Red
    Write-Host ('Log: ' + $taskTranscript)
    exit 1
} finally {
    Stop-Transcript | Out-Null
}
