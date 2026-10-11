import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtCore import Qt
from PySide6.QtGui import QInputMethodEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
import pytest

from translator import ui


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def controller(app, monkeypatch):
    monkeypatch.setattr(ui.Controller, "preload", lambda self: None)
    monkeypatch.setattr(ui.native, "focus", lambda hwnd: True)
    obj = ui.Controller(app, register_hotkeys=False)
    monkeypatch.setattr(obj, "notify", lambda text: None)
    yield obj
    obj.cancel.set()
    obj.pending = None
    obj.popup.hide()
    obj.thread.quit()
    obj.thread.wait(10000)
    obj.tray.hide()
    app.removeNativeEventFilter(obj.hotkeys)


def ready(controller, text="测试", translated="Test"):
    controller.start_popup(text)
    controller.timer.stop()
    controller.popup.output.setPlainText(translated)
    controller.result_revision = controller.revision


def test_close_copies_current_result(controller, app):
    ready(controller)
    controller.popup.close()
    assert app.clipboard().text() == "Test"
    assert not controller.popup.isVisible()


def test_edit_invalidates_old_result(controller, app):
    ready(controller)
    app.clipboard().setText("original")
    controller.popup.source.setPlainText("新的文本")
    controller.popup.close()
    assert app.clipboard().text() == "original"


def test_stale_completion_never_overwrites(controller):
    ready(controller)
    old_revision = controller.revision
    controller.popup.source.setPlainText("新的文本")
    controller.active_job = (old_revision, "测试")
    controller.completed(old_revision, "STALE", "")
    assert not controller.popup.output.toPlainText()


def test_enter_copies_closes_and_pastes(controller, app, monkeypatch):
    calls = []
    ready(controller)
    controller.target = 123
    monkeypatch.setattr(ui.native, "foreground", lambda: 123)
    monkeypatch.setattr(ui.native, "modifiers_pressed", lambda: False)
    monkeypatch.setattr(ui.native, "shortcut", calls.append)
    controller.submit()
    QTest.qWait(200)
    assert app.clipboard().text() == "Test"
    assert not controller.popup.isVisible()
    assert calls == ["V"]


def test_enter_while_loading_and_focus_change(controller, monkeypatch):
    controller.start_popup("测试")
    controller.timer.stop()
    controller.submit()
    assert controller.submit_pending
    calls = []
    controller.target = 123
    monkeypatch.setattr(ui.native, "foreground", lambda: 456)
    monkeypatch.setattr(ui.native, "shortcut", calls.append)
    controller.completed(controller.revision, "Test", "")
    QTest.qWait(180)
    assert not calls
    assert not controller.popup.isVisible()


def test_ime_enter_and_shift_enter(app):
    edit = ui.InputEdit()
    submitted = []
    edit.submit.connect(lambda: submitted.append(True))
    edit.inputMethodEvent(QInputMethodEvent("ni", []))
    QTest.keyClick(edit, Qt.Key.Key_Return)
    assert not submitted
    edit.inputMethodEvent(QInputMethodEvent("", []))
    QTest.keyClick(edit, Qt.Key.Key_Return, Qt.KeyboardModifier.ShiftModifier)
    assert not submitted
    QTest.keyClick(edit, Qt.Key.Key_Return)
    assert submitted == [True]


def test_capture_failure_still_opens_empty_input(controller, app, monkeypatch):
    app.clipboard().setText("old clipboard")
    def fail_copy(letter):
        raise RuntimeError("copy unavailable")
    monkeypatch.setattr(ui.native, "shortcut", fail_copy)
    controller.capture_selection(123)
    assert controller.popup.isVisible()
    assert controller.popup.source.toPlainText() == ""
    assert controller.target == 123
    assert app.clipboard().text() == "old clipboard"


def test_captured_text_remains_editable(controller):
    ready(controller, "原来选中的内容", "Original selection")
    controller.popup.source.setPlainText("现在自己修改内容")
    assert controller.current_result() == ""
    assert controller.timer.isActive()
    assert not controller.popup.source.isReadOnly()
