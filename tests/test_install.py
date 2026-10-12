"""Exercise the installer on a source copy with no Python on PATH."""
import os
from pathlib import Path
import shutil
import subprocess


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
    assert b"Python 3.11 x64 was not found" in result.stdout
    assert (tmp_path / "install.log").is_file()
    assert not (tmp_path / ".venv").exists()
