"""Exercise the installer on a source copy with no Python on PATH."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

import pytest

from scripts.check_runtime import supported_runtime


def test_missing_python_is_an_actionable_failure_not_success(tmp_path):
    root = Path(__file__).resolve().parent.parent
    (tmp_path / "scripts").mkdir()
    shutil.copy2(root / "setup.ps1", tmp_path / "setup.ps1")
    shutil.copy2(root / "scripts" / "check_runtime.py", tmp_path / "scripts" / "check_runtime.py")
    system32 = Path(os.environ["SystemRoot"]) / "System32"
    powershell = system32 / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    env = {**os.environ, "PATH": str(system32)}
    result = subprocess.run([str(powershell), "-NoProfile", "-ExecutionPolicy", "Bypass",
                             "-File", str(tmp_path / "setup.ps1")], cwd=tmp_path,
                            env=env, capture_output=True, timeout=20)
    assert result.returncode == 1
    assert b"Python 3.10-3.13 x64 was not found" in result.stdout
    assert (tmp_path / "install.log").is_file()
    assert not (tmp_path / ".venv").exists()


@pytest.mark.parametrize("version,bits,implementation,free_threaded,expected", [
    ((3, 10, 0), 64, "cpython", False, True),
    ((3, 11, 9), 64, "cpython", False, True),
    ((3, 12, 7), 64, "cpython", False, True),
    ((3, 13, 0), 64, "cpython", False, True),
    ((3, 9, 20), 64, "cpython", False, False),
    ((3, 14, 0), 64, "cpython", False, False),
    ((3, 13, 0), 32, "cpython", False, False),
    ((3, 13, 0), 64, "cpython", True, False),
    ((3, 11, 0), 64, "pypy", False, False),
])
def test_supported_runtime(version, bits, implementation, free_threaded, expected):
    assert supported_runtime(version, bits, implementation, free_threaded) is expected


@pytest.mark.parametrize("setup_exit", [0, 1])
def test_first_run_bat_only_launches_after_success(tmp_path, setup_exit):
    root = Path(__file__).resolve().parent.parent
    work = tmp_path / "中文 folder"
    work.mkdir()
    shutil.copy2(root / "首次运行.bat", work / "首次运行.bat")
    (work / "setup.ps1").write_text(
        f"param([switch]$InstallPython)\nif (-not $InstallPython) {{ exit 9 }}\nexit {setup_exit}\n",
        encoding="ascii")
    runtime = work / ".venv" / "Scripts"
    runtime.mkdir(parents=True)
    # Use a real Python process to observe BAT quoting and --settings delivery.
    shutil.copy2(Path(sys.base_prefix) / "pythonw.exe", runtime / "pythonw.exe")
    (work / ".venv" / "pyvenv.cfg").write_text(f"home = {sys.base_prefix}\n", encoding="utf-8")
    marker = work / "started.txt"
    (work / "main.py").write_text(
        "import pathlib, sys\npathlib.Path(__file__).with_name('started.txt').write_text('|'.join(sys.argv[1:]))\n",
        encoding="ascii")
    result = subprocess.run(["cmd.exe", "/d", "/c", str(work / "首次运行.bat")],
                            input=b"\r\n", capture_output=True, timeout=30)
    assert result.returncode == setup_exit, result.stdout + result.stderr
    if setup_exit == 0:
        deadline = time.monotonic() + 10
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(.1)
        assert marker.read_text() == "--settings"
    else:
        assert not marker.exists()


@pytest.mark.parametrize("status,subject", [
    ("NotSigned", "O=Python Software Foundation"),
    ("Valid", "O=Unrelated Publisher"),
])
def test_download_must_have_valid_python_publisher_signature(tmp_path, status, subject):
    root = Path(__file__).resolve().parent.parent
    shutil.copy2(root / "scripts" / "install_python.ps1", tmp_path / "install_python.ps1")
    # Mock only download/signature/process boundaries; never install on the test host.
    harness = tmp_path / "check.ps1"
    harness.write_text(r"""
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\install_python.ps1"
$env:LOCALAPPDATA = $PSScriptRoot
function Invoke-WebRequest { param($Uri, $OutFile, [switch]$UseBasicParsing)
    if ($Uri -ne 'https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe') { throw 'Unexpected URL' }
    Set-Content -LiteralPath $OutFile -Value 'fake download'
}
function Get-AuthenticodeSignature { param($LiteralPath)
    return [pscustomobject]@{ Status = 'STATUS'; SignerCertificate = [pscustomobject]@{Subject = 'SUBJECT'} }
}
function Start-Process { Set-Content "$PSScriptRoot\executed.txt" 'unsafe'; throw 'Must not execute' }
try { Install-PythonRuntime; exit 9 } catch {
    Write-Host $_.Exception.Message
    if ($_.Exception.Message -like '*signature verification failed*') { exit 0 }
    exit 1
}
""".replace("STATUS", status).replace("SUBJECT", subject), encoding="ascii")
    result = subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                             "-File", str(harness)], capture_output=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
    assert not (tmp_path / "executed.txt").exists()
