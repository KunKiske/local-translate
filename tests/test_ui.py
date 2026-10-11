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
    instance = QApplication.instance() or QApplication([])
    ui.apply_appearance(instance)
    return instance


@pytest.fixture
def controller(app, monkeypatch):
    monkeypatch.setattr(ui.Controller, "preload", lambda self: None)
    monkeypatch.setattr(ui.native, "focus", lambda hwnd: True)
    obj = ui.Controller(app, register_hotkeys=False)
    monkeypatch.setattr(obj, "notify", lambda text: None)
    yield obj
    obj.cancel.set()
    obj.pending = None
    if obj.dialog:
        obj.dialog.finished.disconnect(obj.settings_closed)
        obj.dialog.close()
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


def naming_ready(controller):
    controller.start_popup("玩家移动速度", "naming")
    controller.timer.stop()
    controller.popup.show_candidates([{"name": "playerMoveSpeed", "label": "推荐"},
                                     {"name": "playerSpeed", "label": "简短"}])
    controller.result_revision = controller.revision


def test_click_outputs_exact_candidate_name(controller, app, monkeypatch):
    naming_ready(controller)
    controller.target = 123
    calls = []
    monkeypatch.setattr(ui.native, "foreground", lambda: 123)
    monkeypatch.setattr(ui.native, "modifiers_pressed", lambda: False)
    monkeypatch.setattr(ui.native, "shortcut", calls.append)
    item = controller.popup.candidates.item(1)
    QTest.mouseClick(controller.popup.candidates.viewport(), Qt.MouseButton.LeftButton,
                     pos=controller.popup.candidates.visualItemRect(item).center())
    QTest.qWait(180)
    assert app.clipboard().text() == "playerSpeed"
    assert calls == ["V"]
    assert not controller.popup.isVisible()


def test_mode_switch_invalidates_names_and_retains_target(controller):
    naming_ready(controller)
    controller.target = 123
    revision = controller.revision
    controller.on_hotkey(1)
    assert controller.popup.mode == "translate"
    assert controller.target == 123
    assert controller.popup.source.toPlainText() == "玩家移动速度"
    assert not controller.current_result()
    controller.active_job = (revision, "玩家移动速度")
    controller.completed(revision, [{"name": "staleName", "label": "old"}], "")
    assert not controller.popup.output.toPlainText()


def test_name_format_change_clears_old_candidates(controller):
    naming_ready(controller)
    controller.popup.direction.setCurrentIndex(controller.popup.direction.findData("pascal"))
    assert not controller.current_result()
    assert controller.popup.candidates.count() == 0
    assert controller.timer.isActive()


def test_naming_arrow_selection_and_close_copies_only_name(controller, app):
    naming_ready(controller)
    QTest.keyClick(controller.popup.source, Qt.Key.Key_Down)
    assert controller.current_result() == "playerSpeed"
    controller.popup.close()
    assert app.clipboard().text() == "playerSpeed"


def test_settings_button_opens_owned_dialog_without_copying(controller, app):
    ready(controller)
    app.clipboard().setText("unchanged")
    QTest.mouseClick(controller.popup.settings_button, Qt.MouseButton.LeftButton)
    assert controller.dialog and controller.dialog.isVisible()
    assert controller.dialog.parentWidget() == controller.popup
    controller.popup.close_if_inactive()
    assert controller.popup.isVisible()
    assert app.clipboard().text() == "unchanged"
    controller.dialog.reject()
    assert not controller.popup.settings_open
    assert controller.popup.source.toPlainText() == "测试"


def test_tray_settings_reuses_open_dialog_and_preserves_edits(controller):
    action = next(a for a in controller.menu.actions() if a.text() == "模型与快捷键设置")
    action.trigger()
    first = controller.dialog
    assert first.isVisible()
    first.hotkey.set_shortcut("Ctrl+Alt+T")
    action.trigger()
    assert controller.dialog is first
    assert first.hotkey.text() == "Ctrl+Alt+T"


def test_dropdown_light_palette_and_owner_stays_open(controller, app, monkeypatch):
    from PySide6.QtGui import QPalette
    controller.start_popup("")
    view = controller.popup.direction.view()
    assert view.palette().color(QPalette.ColorRole.Base).lightness() > 230
    assert view.palette().color(QPalette.ColorRole.Text).lightness() < 80
    controller.popup.direction.showPopup()
    monkeypatch.setattr(controller.popup, "isActiveWindow", lambda: False)
    controller.popup.close_if_inactive()
    assert controller.popup.isVisible()
    controller.popup.direction.hidePopup()


def test_shortcut_recording_chord_cancel_and_single_key(controller):
    controller.show_settings()
    button = controller.dialog.hotkey
    QTest.mouseClick(button, Qt.MouseButton.LeftButton)
    assert button.recording
    QTest.keyClick(button, Qt.Key.Key_T, Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier)
    assert button.shortcut == "Ctrl+Alt+T" and not button.recording
    QTest.mouseClick(button, Qt.MouseButton.LeftButton)
    QTest.keyClick(button, Qt.Key.Key_Shift)
    assert button.recording
    QTest.mouseClick(button, Qt.MouseButton.LeftButton)
    assert not button.recording and button.shortcut == "Ctrl+Alt+T"
    QTest.mouseClick(button, Qt.MouseButton.LeftButton)
    QTest.keyClick(button, Qt.Key.Key_F1)
    assert button.shortcut == "F1"


def test_recorder_switch_invalid_key_escape_and_close(controller):
    controller.show_settings()
    dialog = controller.dialog
    QTest.mouseClick(dialog.hotkey, Qt.MouseButton.LeftButton)
    QTest.keyClick(dialog.hotkey, Qt.Key.Key_A)
    assert dialog.hotkey.recording and dialog.hotkey.shortcut == controller.settings.hotkey
    QTest.mouseClick(dialog.dictionary_hotkey, Qt.MouseButton.LeftButton)
    assert not dialog.hotkey.recording and dialog.dictionary_hotkey.recording
    QTest.keyClick(dialog.dictionary_hotkey, Qt.Key.Key_Escape)
    assert dialog.isVisible() and not dialog.dictionary_hotkey.recording
    QTest.mouseClick(dialog.naming_hotkey, Qt.MouseButton.LeftButton)
    dialog.reject()
    assert not any(r.recording for r in dialog.recorders)


def test_dictionary_candidate_click_outputs_only_translation(controller, app, monkeypatch):
    monkeypatch.setattr(controller, "enqueue", lambda text: None)
    controller.start_popup("bank", "dictionary")
    controller.active_job = (controller.revision, "bank")
    controller.completed(controller.revision, [{"name": "银行", "label": "bank · 名词", "detail": "银行", "phonetic": ""},
                                              {"name": "岸", "label": "bank · 名词", "detail": "岸", "phonetic": ""}], "")
    assert controller.popup.candidates.count() == 2
    assert "名词" in controller.popup.candidates.item(1).text()
    chosen = controller.popup.candidates.item(1)
    controller.target = None
    QTest.mouseClick(controller.popup.candidates.viewport(), Qt.MouseButton.LeftButton,
                     pos=controller.popup.candidates.visualItemRect(chosen).center())
    assert not controller.popup.isVisible() and app.clipboard().text() == "岸"


def test_dictionary_no_match_does_not_copy_or_requeue(controller, app, monkeypatch):
    calls = []
    monkeypatch.setattr(controller, "enqueue", calls.append)
    controller.start_popup("notaword", "dictionary")
    controller.active_job = (controller.revision, "notaword")
    app.clipboard().setText("keep")
    controller.completed(controller.revision, [], "")
    controller.submit()
    assert calls == ["notaword"] and not controller.submit_pending
    assert not controller.popup.send.isEnabled()
    assert controller.popup.isVisible()
    controller.popup.close()
    assert app.clipboard().text() == "keep"


def test_dictionary_mode_switch_and_edits_invalidate_results(controller, monkeypatch):
    monkeypatch.setattr(controller, "enqueue", lambda text: None)
    ready(controller, "run", "跑")
    controller.on_hotkey(3)
    assert controller.popup.mode == "dictionary" and controller.popup.source.toPlainText() == "run"
    old = controller.revision
    controller.popup.source.setPlainText("bank")
    controller.active_job = (old, "run")
    controller.completed(old, [{"name": "跑"}], "")
    assert controller.popup.candidates.count() == 0 and controller.timer.isActive()


@pytest.mark.parametrize("ident,mode", [(1, "translate"), (2, "naming"), (3, "dictionary")])
def test_same_hotkey_toggles_closed_and_copies_ready_result(controller, app, monkeypatch, ident, mode):
    monkeypatch.setattr(controller, "enqueue", lambda text: None)
    controller.start_popup("test", mode)
    controller.timer.stop()
    controller.result_revision = controller.revision
    if mode == "translate":
        controller.popup.output.setPlainText("测试")
    else:
        controller.popup.show_candidates([{"name": "测试", "label": "candidate"}])
    controller.on_hotkey(ident)
    assert not controller.popup.isVisible()
    assert app.clipboard().text() == "测试"
    assert not controller.timer.isActive()


def test_toggle_while_working_cancels_without_copying_stale_result(controller, app, monkeypatch):
    monkeypatch.setattr(controller, "enqueue", lambda text: None)
    controller.start_popup("test", "dictionary")
    old_revision = controller.revision
    app.clipboard().setText("keep")
    controller.on_hotkey(3)
    assert not controller.popup.isVisible() and controller.cancel.is_set()
    controller.active_job = (old_revision, "test")
    controller.completed(old_revision, [{"name": "stale"}], "")
    assert app.clipboard().text() == "keep"
    assert not controller.current_result()
