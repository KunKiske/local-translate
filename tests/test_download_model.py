"""Exercise the real PowerShell downloader/curl against a local HTTP server."""
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import threading

import pytest


@pytest.fixture
def source():
    data = b"model bytes for download and resume\n" * 300
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            range_header = self.headers.get("Range")
            calls.append(range_header)
            offset = int(range_header.split("=")[1].split("-")[0]) if range_header else 0
            self.send_response(206 if range_header else 200)
            self.send_header("Content-Length", str(len(data) - offset))
            if range_header:
                self.send_header("Content-Range", f"bytes {offset}-{len(data)-1}/{len(data)}")
            self.end_headers()
            self.wfile.write(data[offset:])

        def log_message(self, *_):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield data, calls, f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def run_download(tmp_path, url, data, checksum=None):
    script = Path(__file__).resolve().parents[1] / "scripts" / "download_model.ps1"
    manifest = {"base_url": url, "files": [{"name": "model.bin", "size": len(data),
                 "sha256": checksum or hashlib.sha256(data).hexdigest()}]}
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    harness = tmp_path / "run.ps1"
    harness.write_text(
        ". '" + str(script).replace("'", "''") + "'\n"
        "$manifest = Get-Content -LiteralPath \"$PSScriptRoot\\manifest.json\" -Raw | ConvertFrom-Json\n"
        "Invoke-ModelDownload -Destination \"$PSScriptRoot\\model folder\" -Manifest $manifest\n",
        encoding="utf-8-sig")
    return subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                           "-File", str(harness)], capture_output=True, timeout=30)


def test_download_and_skip_verified_files(tmp_path, source):
    data, calls, url = source
    result = run_download(tmp_path, url, data)
    assert result.returncode == 0, result.stdout + result.stderr
    assert (tmp_path / "model folder/model.bin").read_bytes() == data
    result = run_download(tmp_path, url, data)
    assert result.returncode == 0, result.stdout + result.stderr
    assert len(calls) == 1


def test_resume_partial_download(tmp_path, source):
    data, calls, url = source
    partial = tmp_path / "model folder/.download/model.bin.partial"
    partial.parent.mkdir(parents=True)
    partial.write_bytes(data[:100])
    result = run_download(tmp_path, url, data)
    assert result.returncode == 0, result.stdout + result.stderr
    assert calls == ["bytes=100-"]
    assert (tmp_path / "model folder/model.bin").read_bytes() == data
    assert not partial.exists()


def test_mismatched_existing_model_is_preserved(tmp_path, source):
    data, calls, url = source
    model = tmp_path / "model folder/model.bin"
    model.parent.mkdir()
    model.write_bytes(b"user model")
    result = run_download(tmp_path, url, data)
    assert result.returncode != 0
    assert model.read_bytes() == b"user model"
    assert calls == []


def test_bad_download_never_becomes_model(tmp_path, source):
    data, _, url = source
    result = run_download(tmp_path, url, data, "0" * 64)
    assert result.returncode != 0
    assert not (tmp_path / "model folder/model.bin").exists()
    assert not (tmp_path / "model folder/.download/model.bin.partial").exists()


def test_full_but_corrupt_partial_is_restarted(tmp_path, source):
    data, calls, url = source
    partial = tmp_path / "model folder/.download/model.bin.partial"
    partial.parent.mkdir(parents=True)
    partial.write_bytes(b"x" * len(data))
    result = run_download(tmp_path, url, data)
    assert result.returncode == 0, result.stdout + result.stderr
    assert calls == [None]
    assert (tmp_path / "model folder/model.bin").read_bytes() == data
