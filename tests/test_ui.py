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
    obj.reading.stop()
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


@pytest.mark.parametrize("selected", [False, True])
def test_capture_opens_quickly_without_reusing_old_clipboard(controller, app, monkeypatch, selected):
    clock = [0.0]
    scheduled = []
    opened = []
    app.clipboard().setText("old clipboard")
    monkeypatch.setattr(ui.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(ui.native, "foreground", lambda: 123)
    monkeypatch.setattr(ui.native, "shortcut", lambda key: None)
    monkeypatch.setattr(ui.native.user32, "GetClipboardSequenceNumber", lambda: 2 if selected and clock[0] >= .03 else 1)
    monkeypatch.setattr(ui.QTimer, "singleShot", lambda delay, callback: scheduled.append((delay, callback)))
    monkeypatch.setattr(controller, "start_popup", lambda text, mode: opened.append((clock[0], text, mode)))
    controller.capture_selection(123, "dictionary")
    while scheduled and not opened:
        delay, callback = scheduled.pop(0)
        clock[0] += delay / 1000
        if selected and clock[0] >= .03:
            app.clipboard().setText("selected text")
        callback()
    assert len(opened) == 1
    assert opened[0][0] <= .131
    assert opened[0][1:] == ("selected text" if selected else "", "dictionary")
    assert app.clipboard().text() == "old clipboard"
    assert not controller.capturing and controller.target == 123


def test_hotkey_copy_waits_for_letter_release_and_aborts_on_focus_change(controller, monkeypatch):
    scheduled, captured = [], []
    held = [True]
    foreground = [123]
    monkeypatch.setattr(ui.QTimer, "singleShot", lambda delay, callback: scheduled.append(callback))
    monkeypatch.setattr(ui.native, "foreground", lambda: foreground[0])
    monkeypatch.setattr(ui.native, "hotkey_pressed", lambda name: held[0])
    monkeypatch.setattr(controller, "capture_selection", lambda target, mode: captured.append((target, mode)))
    controller.on_hotkey(1)
    assert not captured  # Never send Ctrl+C from inside WM_HOTKEY.
    scheduled.pop(0)()
    assert not captured and scheduled
    held[0] = False
    scheduled.pop(0)()
    assert captured == [(123, "translate")]
    controller.on_hotkey(2)
    foreground[0] = 456
    scheduled.pop(0)()
    assert captured == [(123, "translate")]


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


def test_reading_toggle_stops_listener_and_rejects_late_result(controller, monkeypatch):
    calls = []
    monkeypatch.setattr(controller.reading.mouse, "start", lambda: calls.append("start"))
    monkeypatch.setattr(controller.reading.mouse, "stop", lambda: calls.append("stop"))
    controller.on_hotkey(4)
    assert controller.reading.enabled and controller.reading_action.isChecked()
    token = controller.reading.generation
    controller.on_hotkey(4)
    controller.reading.completed(token, "late result", "")
    assert not controller.reading.enabled and not controller.reading_action.isChecked()
    assert not controller.reading.tip.isVisible() and calls == ["start", "stop"]


def test_reading_drag_only_and_skip_own_window(controller, monkeypatch):
    reader = controller.reading
    monkeypatch.setattr(reader.mouse, "start", lambda: None)
    monkeypatch.setattr(reader.mouse, "stop", lambda: None)
    monkeypatch.setattr(ui.native, "foreground", lambda: 123)
    monkeypatch.setattr(ui.native, "modifiers_pressed", lambda: False)
    queued, captured = [], []
    monkeypatch.setattr(ui.QTimer, "singleShot", lambda delay, callback: queued.append(callback))
    monkeypatch.setattr(reader, "capture", lambda token, target: captured.append(target))
    reader.set_enabled(True)
    reader.mouse_event(0x201, 10, 10)
    reader.mouse_event(0x202, 10, 10)
    assert not queued
    reader.mouse_event(0x201, 50, 50)
    reader.mouse_event(0x202, 130, 50)
    queued.pop()()
    assert captured == [123]
    controller.popup.show()
    reader.mouse_event(0x201, 50, 50)
    reader.mouse_event(0x202, 130, 50)
    assert not queued


def test_local_word_tip_without_reading_mode_preserves_sentence_and_clipboard(controller, app, monkeypatch):
    from PySide6.QtCore import QPoint
    from PySide6.QtGui import QTextCursor
    monkeypatch.setattr(controller, "enqueue", lambda text: None)
    ready(controller, "Designing clipboard restoration", "设计剪贴板恢复")
    original_result = controller.current_result()
    cursor = controller.popup.source.textCursor()
    cursor.setPosition(0)
    cursor.setPosition(9, QTextCursor.MoveMode.KeepAnchor)
    controller.popup.source.setTextCursor(cursor)
    monkeypatch.setattr(ui.native, "foreground", lambda: int(controller.popup.winId()))
    jobs = []
    monkeypatch.setattr(controller, "enqueue_reading", lambda token, text: jobs.append((token, text)))
    app.clipboard().setText("unchanged")
    controller.popup.source.selection_requested.emit("Designing", QPoint(100, 100))
    assert not controller.reading.enabled and jobs[-1][1] == "Designing"
    controller.reading.completed(jobs[-1][0], "设计", "")
    assert controller.reading.tip.text.text() == "设计"
    assert controller.reading.tip.isVisible()
    assert controller.current_result() == original_result
    assert controller.popup.source.toPlainText() == "Designing clipboard restoration"
    assert app.clipboard().text() == "unchanged"
    cursor.clearSelection()
    controller.popup.source.setTextCursor(cursor)
    assert not controller.reading.tip.isVisible()


def test_reading_queue_does_not_replace_pending_main_translation(controller, monkeypatch):
    controller.busy = True
    controller.active_job = (1, "loading", "translate")
    main_job = (2, "main text", "translate")
    controller.pending = main_job
    controller.enqueue_reading(10, "word")
    assert controller.pending is main_job
    assert controller.reading_pending[1] == "word"
    dispatched = []
    monkeypatch.setattr(controller, "dispatch", dispatched.append)
    controller.dispatch_next()
    assert dispatched == [main_job]
    controller.dispatch_next()
    assert dispatched[-1][2] == "reading"
    controller.busy = False


def test_simple_preference_saves_without_changing_other_settings(controller, tmp_path, monkeypatch):
    from translator import config
    from dataclasses import asdict
    previous = asdict(controller.settings)
    monkeypatch.setattr(config, "APP_DIR", tmp_path)
    monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "settings.json")
    monkeypatch.setattr(controller.hotkeys, "configure", lambda *args: None)
    controller.show_settings()
    controller.dialog.simple_ui.setChecked(True)
    controller.dialog.save()
    stored = asdict(config.Settings.load())
    assert stored == {**previous, "simple_ui": True}
    assert controller.popup.simple and controller.reading.tip.simple
    action = next(a for a in controller.menu.actions() if a.text() == "模型与快捷键设置")
    action.trigger()
    assert controller.dialog.isVisible() and controller.dialog.simple_ui.isChecked()


def test_simple_ui_keeps_content_and_errors_and_can_restore(controller):
    ready(controller, "hello", "你好")
    popup = controller.popup
    popup.set_simple(True)
    assert popup.header.isHidden() and popup.footer.isHidden() and popup.status.isHidden()
    assert popup.direction.isVisible() and popup.send.isVisible()
    assert popup.mode_label.isVisible() and popup.mode_label.text() == "中英翻译"
    assert popup.source.toPlainText() == "hello" and controller.current_result() == "你好"
    popup.set_status("翻译失败：示例错误", error=True)
    assert popup.status.isVisible()
    popup.set_status("翻译完成")
    assert popup.status.isHidden()
    popup.set_mode("dictionary")
    assert popup.mode_bar.isVisible() and popup.direction.isHidden()
    assert popup.mode_label.isVisible() and popup.mode_label.text() == "离线字典"
    popup.set_mode("naming")
    assert popup.mode_label.isVisible() and popup.mode_label.text() == "代码命名"
    assert popup.direction.isVisible()
    popup.set_mode("dictionary")
    popup.set_simple(False)
    assert popup.header.isVisible() and popup.mode_bar.isVisible() and popup.footer.isVisible()
    assert popup.direction.isVisible()


def test_reading_text_only_tip_offset_and_screen_bounds(app):
    from PySide6.QtCore import QPoint
    from translator.reading import ReadingTip
    tip = ReadingTip()
    area = app.primaryScreen().availableGeometry()
    anchor = area.topLeft() + QPoint(20, 20)
    tip.set_simple(True)
    tip.present("设计", anchor)
    assert tip.title.isHidden() and tip.text.text() == "设计"
    assert tip.pos() == anchor + QPoint(26, 36)
    tip.present("A longer result for screen-edge placement.", area.bottomRight())
    assert area.contains(tip.geometry())
    tip.set_simple(False)
    assert tip.title.isVisible()
    tip.close()
