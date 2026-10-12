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


def test_external_enter_consumes_repeat_and_keyup_after_disarm(monkeypatch):
    observer = native.ExternalEnter()
    received = []
    observer.requested.connect(received.append)
    monkeypatch.setattr(native, "external_focus", lambda: (123, 456))
    monkeypatch.setattr(native, "modifiers_pressed", lambda: False)
    monkeypatch.setattr(native.user32, "CallNextHookEx", lambda *args: 0)
    key = native.KBDLLHOOKSTRUCT(vkCode=0x0D)
    send = lambda message: observer._event(0, message, ctypes.addressof(key))
    assert send(0x100) == 0
    observer.armed = True
    assert send(0x100) == 1
    observer.armed = False  # The queued submission closed the translation popup.
    assert send(0x100) == 1 and send(0x101) == 1
    assert received == [(123, 456)] and not observer.held
    assert send(0x100) == 0


@pytest.mark.parametrize("modified,context,flags,vk", [(True, (123, 456), 0, 13),
    (False, None, 0, 13), (False, (123, 456), 0, 65)])
def test_external_enter_leaves_other_input_alone(monkeypatch, modified, context, flags, vk):
    observer = native.ExternalEnter()
    observer.armed = True
    received = []
    observer.requested.connect(received.append)
    monkeypatch.setattr(native, "external_focus", lambda: context)
    monkeypatch.setattr(native, "modifiers_pressed", lambda: modified)
    monkeypatch.setattr(native.user32, "CallNextHookEx", lambda *args: 0)
    key = native.KBDLLHOOKSTRUCT(vkCode=vk, flags=flags)
    assert observer._event(0, 0x100, ctypes.addressof(key)) == 0
    assert not received
