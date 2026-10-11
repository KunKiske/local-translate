import ctypes
from ctypes import wintypes

import pytest

from translator import native


@pytest.mark.parametrize("mods,alt_down,masked", [(1, True, True), (5, True, True),
                                                (0, True, False), (3, True, False),
                                                (1, False, False)])
def test_alt_mask_does_not_send_character_or_release_user_keys(monkeypatch, mods, alt_down, masked):
    events = []
    monkeypatch.setattr(native.user32, "GetAsyncKeyState", lambda vk: 0x8000 if alt_down else 0)
    def send(count, inputs, size):
        events.extend((inputs[i].ki.wVk, inputs[i].ki.dwFlags) for i in range(count))
        return count
    monkeypatch.setattr(native.user32, "SendInput", send)
    native.mask_alt_menu(mods)
    assert events == ([(0xFF, 0), (0xFF, 2)] if masked else [])


def test_native_filter_masks_before_controller_waits(monkeypatch):
    calls = []
    monkeypatch.setattr(native, "mask_alt_menu", lambda mods: calls.append(("mask", mods)))
    hotkeys = native.Hotkeys(lambda ident: calls.append(("callback", ident)))
    msg = wintypes.MSG(message=0x0312, wParam=1, lParam=(ord("Q") << 16) | 1)
    assert hotkeys.nativeEventFilter(None, ctypes.addressof(msg)) == (True, 0)
    assert calls == [("mask", 1), ("callback", 1)]


def test_hotkey_letter_still_held_blocks_copy(monkeypatch):
    monkeypatch.setattr(native, "modifiers_pressed", lambda: False)
    monkeypatch.setattr(native.user32, "GetAsyncKeyState", lambda vk: 0x8000 if vk == ord("Q") else 0)
    assert native.hotkey_pressed("Alt+Q")
    assert not native.hotkey_pressed("F1")
