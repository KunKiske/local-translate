"""Cross-process Enter/paste regression using only a disposable test editor."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import ctypes
from ctypes import wintypes
import ctranslate2
import tokenizers

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import QMimeData, Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPlainTextEdit
from translator import native
from translator.ui import Controller


def wait_for(predicate):
    deadline = time.monotonic() + 8
    while not predicate():
        if time.monotonic() > deadline:
            raise AssertionError("Timed out waiting for target-editor state")
        QTest.qWait(30)


def activate(hwnd):
    current = ctypes.windll.kernel32.GetCurrentThreadId()
    other = native.user32.GetWindowThreadProcessId(native.foreground(), None)
    native.user32.AttachThreadInput(current, other, True)
    try:
        assert native.focus(hwnd)
    finally:
        native.user32.AttachThreadInput(current, other, False)


def enter():
    events = (native.INPUT * 2)()
    for event, flags in zip(events, (0, 2)):
        event.type = 1
        event.ki = native.KEYBDINPUT(13, 0, flags, 0, 0)
    assert native.user32.SendInput(2, events, ctypes.sizeof(native.INPUT)) == 2


app = QApplication([])
app.setQuitOnLastWindowClosed(False)
if "--editor" in sys.argv:
    folder = Path(sys.argv[-1])
    editor = QPlainTextEdit()
    editor.setWindowTitle("轻译回填测试 · 临时目标")
    editor.resize(500, 220)
    editor.show()
    editor.setFocus()
    editor.textChanged.connect(lambda: (folder / "text.txt").write_text(editor.toPlainText(), encoding="utf-8"))
    (folder / "hwnd.txt").write_text(str(int(editor.winId())))
    QTimer.singleShot(30000, app.quit)
    app.exec()
    raise SystemExit()

original = QMimeData()
mime = app.clipboard().mimeData()
if mime:
    for fmt in mime.formats():
        original.setData(fmt, mime.data(fmt))
Controller.preload = lambda self: None
controller = Controller(app, register_hotkeys=False)
controller.native_input_enabled = True
controller.enqueue = lambda text: None
controller.notify = lambda text: print(text, flush=True)
child = None
try:
    with tempfile.TemporaryDirectory(prefix="localtranslate-target-") as folder_name:
        folder = Path(folder_name)
        child = subprocess.Popen([sys.executable, __file__, "--editor", folder_name])
        wait_for(lambda: (folder / "hwnd.txt").exists())
        hwnd = int((folder / "hwnd.txt").read_text())
        controller.target = None
        controller.start_popup("hello")
        controller.timer.stop()
        controller.popup.output.setPlainText("你好")
        controller.result_revision = controller.revision
        app.clipboard().setText("clipboard-before-confirm")
        activate(hwnd)
        QTest.qWait(200)
        assert controller.popup.isVisible()
        assert app.clipboard().text() == "clipboard-before-confirm"
        assert controller.target == hwnd
        enter()
        wait_for(lambda: (folder / "text.txt").exists() and (folder / "text.txt").read_text(encoding="utf-8") == "你好")
        assert not controller.popup.isVisible()
        enter()
        wait_for(lambda: (folder / "text.txt").read_text(encoding="utf-8") == "你好\n")
        print(json.dumps({"outside_click_keeps_popup": True, "paste_to_new_process": True,
                          "submission_enter_consumed": True, "enter_restored_after_close": True}))
        child.terminate()
        child.wait(timeout=5)
finally:
    if child and child.poll() is None:
        child.terminate()
        child.wait(timeout=5)
    controller.external_enter.stop()
    controller.target_timer.stop()
    controller.quit()
    app.clipboard().setMimeData(original)
