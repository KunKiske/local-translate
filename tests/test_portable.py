import json
import zipfile
from pathlib import Path

import pytest

from translator import config
from scripts.package_portable import package


def test_first_run_finds_model_next_to_exe_and_preserves_existing_config(tmp_path, monkeypatch):
    application = tmp_path / "Program"
    model = application / "models" / "NLLB-600M"
    model.mkdir(parents=True)
    (model / "model.bin").write_bytes(b"weights")
    settings_file = tmp_path / "settings.json"
    monkeypatch.setattr(config.sys, "frozen", True, raising=False)
    monkeypatch.setattr(config.sys, "executable", str(application / "LocalTranslate.exe"))
    monkeypatch.setattr(config, "CONFIG_FILE", settings_file)
    first = config.Settings.load()
    assert Path(first.model_path) == model
    assert first.device == "cpu" and first.compute_type == "int8"
    assert not settings_file.exists()
    original = json.dumps({"model_path": "X:/my-model", "device": "cuda", "hotkey": "Alt+Q", "simple_ui": True})
    settings_file.write_text(original, encoding="utf-8")
    existing = config.Settings.load()
    assert existing.model_path == "X:/my-model" and existing.device == "cuda"
    assert existing.hotkey == "Alt+Q" and existing.simple_ui
    assert settings_file.read_text(encoding="utf-8") == original


def test_package_contains_runtime_model_and_license_but_not_model_cache(tmp_path):
    build = tmp_path / "app"
    (build / "_internal").mkdir(parents=True)
    (build / "LocalTranslate.exe").write_bytes(b"exe")
    (build / "_internal" / "QtCore.dll").write_bytes(b"runtime")
    model = tmp_path / "model"
    model.mkdir()
    for name in ("model.bin", "config.json", "tokenizer.json", "README.md", "LICENSE"):
        (model / name).write_bytes(b"model data")
    (model / "private-cache.txt").write_bytes(b"excluded")
    output = package(build, tmp_path / "release" / "portable.zip", model)
    with zipfile.ZipFile(output) as archive:
        assert archive.testzip() is None
        names = archive.namelist()
        assert "LocalTranslate/_internal/QtCore.dll" in names
        assert "LocalTranslate/models/NLLB-600M/LICENSE" in names
        assert "LocalTranslate/models/NLLB-600M/tokenizer.json" in names
        assert not any("private-cache" in name for name in names)
    assert output.with_suffix(".zip.sha256").is_file()


def test_package_rejects_missing_runtime(tmp_path):
    with pytest.raises(ValueError, match="complete"):
        package(tmp_path, tmp_path / "bad.zip")
