param([switch]$InstallPython)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$taskTranscript = Join-Path $PSScriptRoot 'install.log'
Start-Transcript -Path $taskTranscript -Force | Out-Null
try {
    if (-not (Test-Path -LiteralPath '.\.venv\Scripts\python.exe')) {
        $taskPython = $null
        $taskArguments = @()
        if (Get-Command py -ErrorAction SilentlyContinue) {
            foreach ($taskVersion in @('-3', '-3.13', '-3.12', '-3.11', '-3.10')) {
                & py $taskVersion '.\scripts\check_runtime.py'
                if ($LASTEXITCODE -eq 0) { $taskPython = 'py'; $taskArguments = @($taskVersion); break }
            }
        }
        if (-not $taskPython -and (Get-Command python -ErrorAction SilentlyContinue)) {
            & python '.\scripts\check_runtime.py'
            if ($LASTEXITCODE -eq 0) { $taskPython = 'python' }
        }
        if (-not $taskPython) {
            if ($InstallPython) {
                . (Join-Path $PSScriptRoot 'scripts\install_python.ps1')
                $taskPython = Get-OrInstallPython
            } else {
                throw 'Python 3.10-3.13 x64 was not found. Run the first-run BAT to install Python automatically, or install a supported version and retry install.cmd.'
            }
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
