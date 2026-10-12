# Used only by the explicit first-run installer. Existing app settings are untouched.
function Get-OrInstallPython {
    $taskCandidates = @()
    foreach ($taskMinor in @('313', '312', '311', '310')) {
        $taskCandidates += Join-Path $env:LOCALAPPDATA "Programs\Python\Python$taskMinor\python.exe"
    }
    foreach ($taskHive in @('HKCU:', 'HKLM:')) {
        foreach ($taskVersion in @('3.13', '3.12', '3.11', '3.10')) {
            $taskKey = "$taskHive\Software\Python\PythonCore\$taskVersion\InstallPath"
            if (Test-Path -LiteralPath $taskKey) {
                $taskDirectory = (Get-Item -LiteralPath $taskKey).GetValue('')
                if ($taskDirectory) { $taskCandidates += Join-Path $taskDirectory 'python.exe' }
            }
        }
    }
    foreach ($taskCandidate in ($taskCandidates | Select-Object -Unique)) {
        if (Test-Path -LiteralPath $taskCandidate) {
            & $taskCandidate '.\scripts\check_runtime.py' | Out-Host
            if ($LASTEXITCODE -eq 0) { return $taskCandidate }
        }
    }
    return Install-PythonRuntime
}

function Install-PythonRuntime {
    if (-not [Environment]::Is64BitOperatingSystem) { throw '64-bit Windows is required.' }
    Write-Host 'No compatible Python found. Downloading Python 3.11.9 x64 from python.org...'
    $taskCache = Join-Path $env:LOCALAPPDATA 'LocalTranslate\installer'
    New-Item -ItemType Directory -Path $taskCache -Force | Out-Null
    $taskInstaller = Join-Path $taskCache 'python-3.11.9-amd64.exe'
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    Invoke-WebRequest -UseBasicParsing -Uri 'https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe' -OutFile $taskInstaller
    $taskSignature = Get-AuthenticodeSignature -LiteralPath $taskInstaller
    if ($taskSignature.Status -ne 'Valid' -or
        $taskSignature.SignerCertificate.Subject -notmatch '(?:^|,\s*)O=Python Software Foundation(?:,|$)') {
        throw 'Python installer signature verification failed. Nothing was installed; check your network and retry.'
    }
    Write-Host 'Installing Python for the current user. Please wait...'
    $taskTarget = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python311'
    $taskProcess = Start-Process -FilePath $taskInstaller -WindowStyle Hidden -Wait -PassThru -ArgumentList @(
        '/quiet', 'InstallAllUsers=0', 'Include_launcher=0', 'PrependPath=0',
        'Include_test=0', 'Include_pip=1', 'Shortcuts=0', ('TargetDir="' + $taskTarget + '"')
    )
    if ($taskProcess.ExitCode -notin @(0, 3010)) {
        throw "Python installation failed (exit $($taskProcess.ExitCode)). Install Python 3.10-3.13 x64 manually and retry."
    }
    $taskPythonExe = Join-Path $taskTarget 'python.exe'
    if (-not (Test-Path -LiteralPath $taskPythonExe)) { throw 'Python installation did not create python.exe.' }
    & $taskPythonExe '.\scripts\check_runtime.py' | Out-Host
    if ($LASTEXITCODE -ne 0) { throw 'The installed Python failed its runtime check.' }
    return $taskPythonExe
}
