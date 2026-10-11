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
from translator.ui import Controller, STYLE


def wait_until(predicate, timeout=15):
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() > deadline:
            raise AssertionError("Timed out waiting for UI state")
        QTest.qWait(30)


def key(vk):
    import ctypes
    events = (native.INPUT * 2)()
    for event, flags in zip(events, (0, 2)):
        event.type = 1
        event.ki = native.KEYBDINPUT(vk, 0, flags, 0, 0)
    assert native.user32.SendInput(2, events, ctypes.sizeof(native.INPUT)) == 2


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
app.setStyle("Fusion")
app.setStyleSheet(STYLE)
app.setQuitOnLastWindowClosed(False)
original = QMimeData()
mime = app.clipboard().mimeData()
if mime:
    for fmt in mime.formats():
        original.setData(fmt, mime.data(fmt))
controller = Controller(app)
print('controller created', flush=True)
controller.notify = lambda message: None
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
    key(0x70)  # F1 with no selection must open an empty, editable input.
    print('F1 sent (no selection)', flush=True)
    wait_until(lambda: controller.popup.isVisible())
    assert controller.popup.source.toPlainText() == ""
    assert controller.popup.output.toPlainText() == ""
    assert app.clipboard().text() == "old-clipboard-must-not-be-used"
    assert "未获取" not in controller.popup.status.text()
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
    key(0x70)  # Native F1: Ctrl+C capture from our editor.
    wait_until(lambda: controller.popup.isVisible() and bool(controller.current_result()))
    assert controller.popup.source.toPlainText() == editor.toPlainText()
    assert app.clipboard().text() == "clipboard-before-selection"
    chinese = controller.current_result()
    assert any("\u4e00" <= ch <= "\u9fff" for ch in chinese)
    report["f1_capture_and_restore"] = chinese
    # A genuine foreground change exercises outside-click dismissal behavior.
    editor.activateWindow()
    native.focus(int(editor.winId()))
    wait_until(lambda: not controller.popup.isVisible())
    assert app.clipboard().text() == chinese
    report["deactivate_closes_and_copies"] = True
    # F2 belongs to other applications again.
    assert native.user32.RegisterHotKey(None, 99, 0x4000, 0x71)
    native.user32.UnregisterHotKey(None, 99)
    report["f2_released"] = True
    (preview.parent / "native-test.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=True))
finally:
    controller.cancel.set()
    wait_until(lambda: not controller.busy)
    controller.quit()
    editor.close()
    app.clipboard().setMimeData(original)
