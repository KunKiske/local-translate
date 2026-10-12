"""Interactive Win32 integration test using only our own disposable editor."""
import json
from pathlib import Path
import sys
import time
import ctypes
from ctypes import wintypes
import ctranslate2
import tokenizers

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QMimeData, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPlainTextEdit

from translator import native
from translator.ui import Controller, apply_appearance


def wait_until(predicate, timeout=15):
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() > deadline:
            if 'controller' in globals():
                print('UI timeout:', controller.popup.mode, controller.popup.isVisible(), controller.popup.isActiveWindow(),
                      controller.popup.status.text(), controller.revision, controller.result_revision,
                      'busy', controller.busy, 'foreground', native.foreground(), 'keys', controller.hotkeys.keys, flush=True)
            raise AssertionError("Timed out waiting for UI state")
        QTest.qWait(30)


def key(vk):
    import ctypes
    events = (native.INPUT * 2)()
    for event, flags in zip(events, (0, 2)):
        event.type = 1
        event.ki = native.KEYBDINPUT(vk, 0, flags, 0, 0)
    assert native.user32.SendInput(2, events, ctypes.sizeof(native.INPUT)) == 2


def hotkey(ident):
    settings = controller.settings
    name = {1: settings.hotkey, 2: settings.naming_hotkey, 3: settings.dictionary_hotkey}[ident]
    mods, vk = native.parse_hotkey(name)
    held = [code for flag, code in ((2, 0x11), (1, 0x12), (4, 0x10), (8, 0x5B)) if mods & flag]
    presses = [(code, 0) for code in held] + [(vk, 0), (vk, 2)] + [(code, 2) for code in reversed(held)]
    events = (native.INPUT * len(presses))()
    for event, (code, flags) in zip(events, presses):
        event.type = 1
        event.ki = native.KEYBDINPUT(code, 0, flags, 0, 0)
    assert native.user32.SendInput(len(events), events, ctypes.sizeof(native.INPUT)) == len(events)


def activate_editor(editor):
    # Test setup starts in a background shell; attach only long enough to focus
    # the disposable test editor. The product never forces a background window.
    native.user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    native.user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    current = ctypes.windll.kernel32.GetCurrentThreadId()
    foreground_thread = native.user32.GetWindowThreadProcessId(native.foreground(), None)
    native.user32.AttachThreadInput(current, foreground_thread, True)
    try:
        editor.activateWindow()
        editor.raise_()
        native.focus(int(editor.winId()))
    finally:
        native.user32.AttachThreadInput(current, foreground_thread, False)
    QTest.qWait(150)
    assert native.foreground() == int(editor.winId()), "Could not focus disposable test editor"


app = QApplication([])
apply_appearance(app)
app.setQuitOnLastWindowClosed(False)
original = QMimeData()
mime = app.clipboard().mimeData()
if mime:
    for fmt in mime.formats():
        original.setData(fmt, mime.data(fmt))
if "--latency-only" in sys.argv:
    Controller.preload = lambda self: None
controller = Controller(app)
print('controller created', flush=True)
controller.notify = lambda message: None
original_present = controller.popup.present
def traced_present():
    before_present = time.perf_counter()
    original_present()
    print('popup foreground:', controller.popup.mode, native.foreground() == int(controller.popup.winId()),
          'present_ms', round((time.perf_counter() - before_present) * 1000, 1), flush=True)
controller.popup.present = traced_present
editor = QPlainTextEdit()
editor.setWindowTitle("轻译 · 自动验证用临时输入框")
editor.resize(650, 300)
editor.move(50, 50)
report = {}
try:
    wait_until(lambda: not controller.busy)
    print('model ready', flush=True)
    editor.show()
    editor.setFocus()
    activate_editor(editor)
    QTest.qWait(200)
    editor.setPlainText("Existing text without a selection.")
    app.clipboard().setText("old-clipboard-must-not-be-used")
    opened_at = time.perf_counter()
    hotkey(1)  # Configured translation shortcut with no selection.
    print('F1 sent (no selection)', flush=True)
    wait_until(lambda: controller.popup.isVisible())
    report["f1_no_selection_open_ms"] = round((time.perf_counter() - opened_at) * 1000, 1)
    assert controller.popup.source.toPlainText() == ""
    assert controller.popup.output.toPlainText() == ""
    assert app.clipboard().text() == "old-clipboard-must-not-be-used"
    assert "未获取" not in controller.popup.status.text()
    if "--latency-only" in sys.argv:
        print(json.dumps(report), flush=True)
        raise SystemExit(0)
    controller.popup.source.setPlainText("你好，今天很高兴见到你。")
    wait_until(lambda: bool(controller.current_result()))
    english = controller.current_result()
    assert "see you" in english.lower(), english
    preview = Path(__file__).resolve().parents[1] / "docs" / "preview.png"
    preview.parent.mkdir(exist_ok=True)
    controller.popup.grab().save(str(preview))
    key(0x0D)
    wait_until(lambda: english in editor.toPlainText())
    assert not controller.popup.isVisible()
    report["f1_no_selection_input_and_enter_paste"] = english

    editor.setPlainText("Please send me the document tomorrow.")
    editor.selectAll()
    app.clipboard().setText("clipboard-before-selection")
    assert native.focus(int(editor.winId()))
    QTest.qWait(150)
    hotkey(1)  # Native shortcut: Ctrl+C capture from our editor.
    wait_until(lambda: controller.popup.isVisible() and bool(controller.current_result()))
    assert controller.popup.source.toPlainText() == editor.toPlainText()
    assert app.clipboard().text() == "clipboard-before-selection"
    chinese = controller.current_result()
    assert any("\u4e00" <= ch <= "\u9fff" for ch in chinese)
    report["f1_capture_and_restore"] = chinese
    # Losing focus keeps the popup open and leaves the clipboard untouched.
    editor.activateWindow()
    native.focus(int(editor.winId()))
    QTest.qWait(200)
    assert controller.popup.isVisible()
    assert app.clipboard().text() == "clipboard-before-selection"
    controller.popup.close()
    assert app.clipboard().text() == chinese
    report["deactivate_keeps_popup_and_explicit_close_copies"] = True
    editor.setPlainText("玩家移动速度")
    editor.selectAll()
    activate_editor(editor)
    hotkey(2)
    wait_until(lambda: controller.popup.isVisible() and controller.popup.candidates.count() >= 3)
    assert controller.popup.mode == "naming"
    assert controller.popup.source.toPlainText() == "玩家移动速度"
    assert controller.current_result() == "playerMoveSpeed"
    controller.popup.grab().save(str(preview.parent / "naming-preview.png"))
    chosen = controller.popup.candidates.item(2)
    chosen_name = chosen.data(Qt.ItemDataRole.UserRole)
    QTest.mouseClick(controller.popup.candidates.viewport(), Qt.MouseButton.LeftButton,
                     pos=controller.popup.candidates.visualItemRect(chosen).center())
    wait_until(lambda: not controller.popup.isVisible() and editor.toPlainText() == chosen_name)
    assert app.clipboard().text() == chosen_name
    report["f2_capture_click_third_candidate_paste"] = chosen_name

    editor.clear()
    activate_editor(editor)
    hotkey(2)
    wait_until(lambda: controller.popup.isVisible())
    assert controller.popup.mode == "naming" and not controller.popup.source.toPlainText()
    controller.popup.source.setPlainText("订单缓存管理器")
    controller.popup.direction.setCurrentIndex(controller.popup.direction.findData("pascal"))
    wait_until(lambda: bool(controller.current_result()))
    assert controller.current_result() == "OrderCacheManager"
    key(0x0D)
    wait_until(lambda: editor.toPlainText() == "OrderCacheManager")
    report["f2_empty_input_pascal_enter"] = editor.toPlainText()

    editor.setPlainText("bank")
    editor.selectAll()
    activate_editor(editor)
    hotkey(3)
    wait_until(lambda: controller.popup.isVisible() and controller.popup.candidates.count() > 1)
    wait_until(lambda: controller.popup.isActiveWindow())
    QTest.qWait(150)
    assert controller.popup.mode == "dictionary" and controller.popup.source.toPlainText() == "bank"
    assert any("名词" in controller.popup.candidates.item(i).text() for i in range(controller.popup.candidates.count()))
    print('before edit', native.foreground(), int(controller.popup.winId()), controller.popup.isActiveWindow(), controller.revision, flush=True)
    controller.popup.source.setPlainText("速度")
    print('after edit', native.foreground(), int(controller.popup.winId()), controller.popup.isActiveWindow(), controller.revision, flush=True)
    try:
        wait_until(lambda: controller.current_result() and controller.popup.candidates.count() > 1)
    except AssertionError:
        print('dictionary state:', controller.popup.status.text(), controller.popup.isVisible(), controller.busy, controller.revision, controller.result_revision, flush=True)
        raise
    assert any(controller.popup.candidates.item(i).data(Qt.ItemDataRole.UserRole) == "speed" for i in range(controller.popup.candidates.count()))
    controller.popup.grab().save(str(preview.parent / "dictionary-preview.png"))
    chosen = controller.popup.candidates.item(1)
    selected_word = chosen.data(Qt.ItemDataRole.UserRole)
    QTest.mouseClick(controller.popup.candidates.viewport(), Qt.MouseButton.LeftButton,
                     pos=controller.popup.candidates.visualItemRect(chosen).center())
    wait_until(lambda: not controller.popup.isVisible() and editor.toPlainText() == selected_word)
    report["f3_capture_edit_chinese_click_paste"] = selected_word

    editor.clear()
    activate_editor(editor)
    hotkey(3)
    wait_until(lambda: controller.popup.isVisible())
    assert not controller.popup.source.toPlainText()
    controller.popup.source.setPlainText("bank")
    wait_until(lambda: controller.current_result() == "银行")
    key(0x0D)
    wait_until(lambda: editor.toPlainText() == "银行")
    report["f3_empty_input_enter_paste"] = True

    editor.clear()
    activate_editor(editor)
    hotkey(1)
    wait_until(lambda: controller.popup.isVisible())
    controller.popup.source.setPlainText("retain this input")
    QTest.mouseClick(controller.popup.settings_button, Qt.MouseButton.LeftButton)
    wait_until(lambda: controller.dialog is not None and controller.dialog.isVisible())
    dialog = controller.dialog
    wait_until(lambda: native.foreground() == int(dialog.winId()))
    QTest.qWait(200)
    assert controller.popup.isVisible(), "Settings must not dismiss its owner"
    assert controller.hotkeys.keys is None
    QTest.mouseClick(dialog.hotkey, Qt.MouseButton.LeftButton)
    hotkey(1)
    wait_until(lambda: not dialog.hotkey.recording)
    assert dialog.hotkey.shortcut == controller.settings.hotkey, "Current global shortcut must be recordable"
    QTest.mouseClick(dialog.hotkey, Qt.MouseButton.LeftButton)
    QTest.keyClick(dialog.hotkey, Qt.Key.Key_T, Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier)
    assert dialog.hotkey.shortcut == "Ctrl+Alt+T"
    QTest.mouseClick(dialog.hotkey, Qt.MouseButton.LeftButton)
    QTest.mouseClick(dialog.hotkey, Qt.MouseButton.LeftButton)
    assert not dialog.hotkey.recording and dialog.hotkey.shortcut == "Ctrl+Alt+T"
    report["record_existing_hotkey_chord_and_cancel"] = True
    dialog.grab().save(str(preview.parent / "settings-preview.png"))
    dialog.device.showPopup()
    QTest.qWait(180)
    assert dialog.device.view().isVisible()
    dialog.device.view().window().grab().save(str(preview.parent / "settings-dropdown.png"))
    from PySide6.QtGui import QPalette
    assert dialog.device.view().palette().color(QPalette.ColorRole.Base).lightness() > 230
    dialog.device.hidePopup()
    dialog.reject()
    assert controller.hotkeys.keys is not None
    wait_until(lambda: controller.popup.isActiveWindow())
    assert controller.popup.source.toPlainText() == "retain this input"
    controller.popup.direction.showPopup()
    QTest.qWait(200)
    assert controller.popup.isVisible()
    view = controller.popup.direction.view()
    item_rect = view.visualRect(view.model().index(1, 0))
    QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=item_rect.center())
    wait_until(lambda: controller.popup.direction.currentData() == "zh-en")
    assert controller.popup.isVisible()
    report["settings_button_foreground_and_dropdown_selection"] = True

    controller.popup.close()
    action = next(a for a in controller.menu.actions() if a.text() == "模型与快捷键设置")
    action.trigger()
    wait_until(lambda: controller.dialog.isVisible())
    dialog = controller.dialog
    wait_until(lambda: native.foreground() == int(dialog.winId()))
    dialog.hotkey.set_shortcut("Ctrl+Alt+T")
    dialog.showMinimized()
    QTest.qWait(100)
    action.trigger()
    wait_until(lambda: not dialog.isMinimized() and native.foreground() == int(dialog.winId()))
    assert controller.dialog is dialog and dialog.hotkey.text() == "Ctrl+Alt+T"
    dialog.reject()
    report["tray_settings_restore_existing_window"] = True
    (preview.parent / "native-test.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=True))
finally:
    controller.cancel.set()
    wait_until(lambda: not controller.busy)
    controller.quit()
    editor.close()
    app.clipboard().setMimeData(original)
