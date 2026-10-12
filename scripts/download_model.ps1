param([string]$Destination = (Join-Path (Split-Path $PSScriptRoot -Parent) 'models\NLLB-600M'))
$ErrorActionPreference = 'Stop'

function Test-ModelFile($Path, $Entry) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf) -or
        (Get-Item -LiteralPath $Path).Length -ne $Entry.size) { return $false }
    $taskHasher = [Security.Cryptography.SHA256]::Create()
    $taskStream = [IO.File]::OpenRead($Path)
    try {
        $taskHash = [BitConverter]::ToString($taskHasher.ComputeHash($taskStream)).Replace('-', '')
        return $taskHash -eq $Entry.sha256
    } finally {
        $taskStream.Dispose()
        $taskHasher.Dispose()
    }
}

function Invoke-ModelDownload($Destination, $Manifest) {
    $taskDestination = [IO.Path]::GetFullPath($Destination)
    # Validate every existing final file before downloading or replacing anything.
    foreach ($taskEntry in $Manifest.files) {
        if ($taskEntry.name -notmatch '^[A-Za-z0-9_.-]+$' -or $taskEntry.name -in @('.', '..')) {
            throw 'Invalid model file name in manifest.'
        }
        $taskFinal = Join-Path $taskDestination $taskEntry.name
        if ((Test-Path -LiteralPath $taskFinal) -and -not (Test-ModelFile $taskFinal $taskEntry)) {
            throw "Existing file differs from the download: $taskFinal . It was preserved. Choose an empty destination folder."
        }
    }
    $taskCurl = Get-Command curl.exe -ErrorAction SilentlyContinue
    if (-not $taskCurl) { throw 'curl.exe was not found. Use an up-to-date Windows 10/11 installation.' }
    New-Item -ItemType Directory -Path $taskDestination -Force | Out-Null
    $taskStaging = Join-Path $taskDestination '.download'
    New-Item -ItemType Directory -Path $taskStaging -Force | Out-Null
    try {
        $taskLock = [IO.File]::Open((Join-Path $taskStaging 'download.lock'), 'OpenOrCreate', 'ReadWrite', 'None')
    } catch { throw 'Another model download is using this folder. Wait for it to finish.' }
    try {
        # model.bin is installed last, so an interrupted initial download is not detected as ready.
        foreach ($taskEntry in ($Manifest.files | Sort-Object @{Expression={$_.name -eq 'model.bin'}}, name)) {
            $taskFinal = Join-Path $taskDestination $taskEntry.name
            if (Test-ModelFile $taskFinal $taskEntry) {
                Write-Host "Verified, skipping: $($taskEntry.name)"
                continue
            }
            $taskPartial = Join-Path $taskStaging ($taskEntry.name + '.partial')
            if (-not (Test-ModelFile $taskPartial $taskEntry)) {
                if ((Test-Path -LiteralPath $taskPartial) -and (Get-Item -LiteralPath $taskPartial).Length -ge $taskEntry.size) {
                    Remove-Item -LiteralPath $taskPartial -Force
                }
                Write-Host "Downloading: $($taskEntry.name)"
                $taskUrl = $Manifest.base_url.TrimEnd('/') + '/' + $taskEntry.name
                $taskProxyArguments = @()
                if (-not $env:HTTPS_PROXY -and -not $env:ALL_PROXY -and -not $env:NO_PROXY) {
                    $taskSystemProxy = [Net.WebRequest]::GetSystemWebProxy()
                    $taskUri = [Uri]$taskUrl
                    if (-not $taskSystemProxy.IsBypassed($taskUri)) {
                        $taskProxy = $taskSystemProxy.GetProxy($taskUri)
                        if ($taskProxy -and $taskProxy -ne $taskUri) {
                            $taskProxyArguments = @('--proxy', $taskProxy.AbsoluteUri)
                        }
                    }
                }
                & $taskCurl.Source @taskProxyArguments --fail --location --retry 3 --retry-delay 2 --connect-timeout 20 --speed-time 60 --speed-limit 1024 --continue-at - --output $taskPartial $taskUrl
                $taskCode = $LASTEXITCODE
                if ($taskCode -in @(33, 36)) {
                    # The server rejected byte ranges. Retry this staging file from the start.
                    & $taskCurl.Source @taskProxyArguments --fail --location --retry 3 --retry-delay 2 --connect-timeout 20 --speed-time 60 --speed-limit 1024 --output $taskPartial $taskUrl
                    $taskCode = $LASTEXITCODE
                }
                if ($taskCode -ne 0) { throw "Download interrupted (curl exit $taskCode). Run the BAT again to resume: $($taskEntry.name)" }
            }
            if (-not (Test-ModelFile $taskPartial $taskEntry)) {
                # Remove only this known staging file, never an existing model file.
                Remove-Item -LiteralPath $taskPartial -Force
                throw "Checksum mismatch: $($taskEntry.name). The incomplete download was discarded. Please retry."
            }
            # Do not overwrite a file created by another process during the download.
            Move-Item -LiteralPath $taskPartial -Destination $taskFinal -ErrorAction Stop
            Write-Host "Verified: $($taskEntry.name)"
        }
        Write-Host "Model ready: $taskDestination"
        Write-Host 'Choose this folder in LocalTranslate settings; CPU + int8 works without CUDA.'
        Write-Host 'Existing model paths, hotkeys and preferences have not been changed.'
    } finally { $taskLock.Dispose() }
}

if ($MyInvocation.InvocationName -ne '.') {
    $taskRoot = Split-Path $PSScriptRoot -Parent
    $taskLog = Join-Path $taskRoot 'download-model.log'
    Start-Transcript -Path $taskLog -Force | Out-Null
    try {
        $taskManifest = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'model_manifest.json') -Raw | ConvertFrom-Json
        Invoke-ModelDownload -Destination $Destination -Manifest $taskManifest
    } catch {
        Write-Host ('DOWNLOAD FAILED: ' + $_.Exception.Message) -ForegroundColor Red
        Write-Host "Log: $taskLog"
        exit 1
    } finally {
        Stop-Transcript | Out-Null
    }
}
