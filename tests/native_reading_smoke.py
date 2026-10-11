"""Exercise the actual mouse hook and non-activating tips in our disposable editor."""
import ctypes
from ctypes import wintypes
import json
from pathlib import Path
import sys
import time
import ctranslate2
import tokenizers

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import QMimeData
from PySide6.QtGui import QTextCursor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPlainTextEdit
from translator import native
from translator.config import CONFIG_FILE
from translator.ui import Controller, apply_appearance


def wait_for(condition, timeout=20):
    deadline = time.monotonic() + timeout
    while not condition():
        if time.monotonic() > deadline:
            raise AssertionError(f"Timed out: enabled={c.reading.enabled}, busy={c.busy}, tip={c.reading.tip.text.text()!r}, foreground={native.foreground()}")
        QTest.qWait(20)


def focus(widget):
    native.user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    thread = native.user32.GetWindowThreadProcessId(native.foreground(), None)
    current = ctypes.windll.kernel32.GetCurrentThreadId()
    native.user32.AttachThreadInput(current, thread, True)
    try:
        widget.raise_()
        widget.activateWindow()
        native.focus(int(widget.winId()))
    finally:
        native.user32.AttachThreadInput(current, thread, False)
    QTest.qWait(80)
    assert native.foreground() == int(widget.winId())


def send_reading_hotkey():
    mods, vk = native.parse_hotkey(c.settings.reading_hotkey)
    held = [code for flag, code in ((2, 0x11), (1, 0x12), (4, 0x10), (8, 0x5B)) if mods & flag]
    presses = [(code, 0) for code in held] + [(vk, 0), (vk, 2)] + [(code, 2) for code in reversed(held)]
    events = (native.INPUT * len(presses))()
    for event, (code, flags) in zip(events, presses):
        event.type = 1
        event.ki = native.KEYBDINPUT(code, 0, flags, 0, 0)
    assert native.user32.SendInput(len(events), events, ctypes.sizeof(native.INPUT)) == len(events)
    QTest.qWait(60)


def drag_text(widget, start, end):
    focus(widget.window())
    # Selecting inside an existing highlight would start Qt's blocking drag/drop
    # loop. Clear only our test editor's old highlight before the next gesture.
    cursor = widget.textCursor()
    cursor.clearSelection()
    widget.setTextCursor(cursor)
    native.user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
    native.user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
    points = []
    for position in (start, end):
        cursor = widget.textCursor()
        cursor.setPosition(position)
        rect = widget.cursorRect(cursor)
        logical = widget.viewport().mapTo(widget.window(), rect.center())
        point = wintypes.POINT(round(logical.x() * widget.devicePixelRatioF()), round(logical.y() * widget.devicePixelRatioF()))
        assert native.user32.ClientToScreen(int(widget.window().winId()), ctypes.byref(point))
        points.append(point)
    native.user32.SetCursorPos(points[0].x, points[0].y)
    print('drag points', [(p.x, p.y) for p in points], 'ratio', widget.devicePixelRatioF(), flush=True)
    QTest.qWait(30)
    def button(flags):
        event = native.INPUT()
        event.type = 0
        event.mi = native.MOUSEINPUT(0, 0, 0, flags, 0, 0)
        assert native.user32.SendInput(1, ctypes.byref(event), ctypes.sizeof(native.INPUT)) == 1
    button(2)
    QTest.qWait(35)
    native.user32.SetCursorPos(points[1].x, points[1].y)
    QTest.qWait(50)
    print('selection before release', repr(widget.textCursor().selectedText()), 'fg', native.foreground(), int(widget.window().winId()), flush=True)
    button(4)
    QTest.qWait(45)


app = QApplication([])
apply_appearance(app)
app.setQuitOnLastWindowClosed(False)
config_before = CONFIG_FILE.read_bytes()
original = QMimeData()
mime = app.clipboard().mimeData()
if mime:
    for fmt in mime.formats():
        original.setData(fmt, mime.data(fmt))
c = Controller(app)
print('controller created', flush=True)
c.notify = lambda message: None
editor = QPlainTextEdit()
editor.setWindowTitle("轻译 · 阅读模式验证用临时编辑框")
editor.resize(650, 250)
editor.move(50, 50)
report = {}
try:
    wait_for(lambda: not c.busy)
    print('model ready', flush=True)
    editor.setPlainText("Hello world.")
    editor.show()
    focus(editor)
    print('editor focused', flush=True)
    app.clipboard().setText("reading-clipboard-original")
    send_reading_hotkey()
    print('reading toggled', c.reading.enabled, flush=True)
    assert c.reading.enabled and c.reading.mouse.handle
    drag_text(editor, 0, len(editor.toPlainText()))
    print('dragged', editor.textCursor().selectedText(), flush=True)
    assert editor.textCursor().hasSelection()
    wait_for(lambda: c.reading.tip.isVisible() and "自动中英互译" in c.reading.tip.title.text())
    assert any('\u4e00' <= char <= '\u9fff' for char in c.reading.tip.text.text())
    assert native.foreground() == int(editor.winId())
    assert app.clipboard().text() == "reading-clipboard-original"
    report["reading_drag_translation"] = c.reading.tip.text.text()
    report["tip_preserves_foreground_and_clipboard"] = True
    c.reading.tip.grab().save("docs/reading-tip-preview.png")
    editor.setPlainText("Good morning.")
    drag_text(editor, 0, len(editor.toPlainText()))
    wait_for(lambda: c.reading.tip.isVisible() and "自动中英互译" in c.reading.tip.title.text())
    report["next_selection_translation"] = c.reading.tip.text.text()
    send_reading_hotkey()
    assert not c.reading.enabled and not c.reading.mouse.handle
    assert not c.reading.tip.isVisible()
    drag_text(editor, 0, 4)
    QTest.qWait(350)
    assert not c.reading.tip.isVisible()
    report["toggle_off_stops_selection_translation"] = True

    c.target = int(editor.winId())
    c.start_popup("Designing clipboard restoration")
    focus(c.popup)
    wait_for(lambda: bool(c.current_result()))
    full_result = c.current_result()
    clip_before = app.clipboard().text()
    drag_text(c.popup.source, 0, 9)
    assert c.popup.source.textCursor().selectedText() == "Designing"
    wait_for(lambda: c.reading.tip.isVisible() and "自动中英互译" in c.reading.tip.title.text())
    assert not c.reading.enabled
    assert c.current_result() == full_result
    assert c.popup.source.toPlainText() == "Designing clipboard restoration"
    assert native.foreground() == int(c.popup.winId()) and c.popup.isVisible()
    assert app.clipboard().text() == clip_before
    report["input_word_tip_without_reading_mode"] = c.reading.tip.text.text()
    c.reading.tip.grab().save("docs/input-word-tip-preview.png")
    c.popup.close()
    assert not c.reading.tip.isVisible()
    assert CONFIG_FILE.read_bytes() == config_before
    report["configuration_unchanged"] = True
    Path("docs/reading-test.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=True), flush=True)
finally:
    c.reading.stop()
    c.cancel.set()
    c.pending = None
    wait_for(lambda: not c.busy)
    c.quit()
    editor.close()
    app.clipboard().setMimeData(original)
