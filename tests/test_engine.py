from pathlib import Path

import pytest

from translator.config import Settings
from translator.engine import TranslationEngine, language_pair, validate_model
from translator.native import parse_hotkey


def test_direction_and_override():
    assert language_pair("Hello") == ("eng_Latn", "zho_Hans")
    assert language_pair("请 review 这份文档") == ("zho_Hans", "eng_Latn")
    assert language_pair("Hello", "zh-en") == ("zho_Hans", "eng_Latn")


def test_hotkey_validation():
    assert parse_hotkey("F1") == (0x4000, 0x70)
    assert parse_hotkey("Ctrl+Alt+T") == (0x4003, ord("T"))
    for invalid in ("F12", "A", "Ctrl+", "Meta+X"):
        with pytest.raises(ValueError):
            parse_hotkey(invalid)


def test_three_hotkeys_conflict_and_registration_rollback(monkeypatch):
    from translator import native
    occupied = {}
    def register(hwnd, ident, mods, vk):
        if vk == ord("X"):
            return False
        occupied[ident] = (mods, vk)
        return True
    monkeypatch.setattr(native.user32, "RegisterHotKey", register)
    monkeypatch.setattr(native.user32, "UnregisterHotKey", lambda hwnd, ident: occupied.pop(ident, None))
    keys = native.Hotkeys(lambda ident: None)
    keys.configure("F1", "F2", "F3")
    previous = dict(occupied)
    with pytest.raises(ValueError, match="相同"):
        keys.configure("F1", "F2", "F1")
    assert occupied == previous
    with pytest.raises(ValueError, match="占用"):
        keys.configure("Ctrl+Alt+T", "F2", "Ctrl+X")
    assert occupied == previous
    assert keys.keys == list(previous.values())
    keys.unregister()
    assert not occupied


def test_missing_model(tmp_path):
    with pytest.raises(ValueError, match="model.bin"):
        validate_model(str(tmp_path))


def test_settings_upgrade_keeps_model_and_one_shortcut(tmp_path, monkeypatch):
    import json
    from translator import config
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"model_path": "custom-model", "selection_key": "Ctrl+Alt+T",
                                "input_key": "F2", "debounce_ms": 700}), encoding="utf-8")
    monkeypatch.setattr(config, "CONFIG_FILE", path)
    monkeypatch.setattr(config, "APP_DIR", tmp_path)
    settings = Settings.load()
    assert settings.hotkey == "Ctrl+Alt+T"
    assert settings.model_path == "custom-model"
    assert settings.debounce_ms == 700
    settings.save()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert "input_key" not in data and "selection_key" not in data
    assert data["hotkey"] == "Ctrl+Alt+T"


def test_reading_default_preserves_existing_configuration_bytes(tmp_path, monkeypatch):
    import json
    from translator import config
    path = tmp_path / "settings.json"
    existing = {"model_path": "my-model", "device": "cuda", "compute_type": "float16",
                "hotkey": "Alt+Q", "naming_hotkey": "Alt+E", "dictionary_hotkey": "Alt+W", "debounce_ms": 100}
    path.write_text(json.dumps(existing), encoding="utf-8")
    original = path.read_bytes()
    monkeypatch.setattr(config, "CONFIG_FILE", path)
    settings = Settings.load()
    assert settings.reading_hotkey == "F4"
    assert all(getattr(settings, key) == value for key, value in existing.items())
    assert path.read_bytes() == original


@pytest.mark.skipif(not Path(Settings().model_path).is_dir(), reason="Local model not installed")
def test_real_model_bidirectional():
    engine = TranslationEngine()
    english = engine.translate("你好，今天很高兴见到你。", "auto", Settings())
    chinese = engine.translate("Please send me the document tomorrow.", "auto", Settings())
    assert "see you" in english.lower()
    assert any("\u4e00" <= c <= "\u9fff" for c in chinese)
    paragraphs = engine.translate("Hello.\n\nGood morning.", "auto", Settings())
    assert "\n\n" in paragraphs
    with pytest.raises(ValueError, match="6000"):
        engine.translate("x" * 6001, "auto", Settings())
    with pytest.raises(InterruptedError):
        engine.translate("Hello.", "auto", Settings(), lambda: True)

