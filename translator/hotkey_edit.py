"""Click-to-record shortcut control; only listens while this dialog is active."""
from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtWidgets import QApplication, QPushButton
from .native import parse_hotkey


class HotkeyButton(QPushButton):
    started = Signal(object)

    def __init__(self, shortcut):
        super().__init__(shortcut)
        self.shortcut = shortcut
        self.recording = False
        self.setAutoDefault(False)
        self.setToolTip("点击后按下单键或组合键；再次点击或 Esc 取消录制")
        self.clicked.connect(self.toggle)

    def set_shortcut(self, shortcut):
        parse_hotkey(shortcut)
        self.shortcut = shortcut
        self.setText(shortcut)

    def toggle(self):
        if self.recording:
            self.cancel()
        else:
            self.started.emit(self)
            self.recording = True
            self.setText("请按快捷键…（再次点击取消）")
            self.setFocus()
            QApplication.instance().installEventFilter(self)

    def cancel(self):
        self.recording = False
        QApplication.instance().removeEventFilter(self)
        self.setText(self.shortcut)

    def eventFilter(self, watched, event):
        if not self.recording:
            return False
        if event.type() == QEvent.Type.WindowDeactivate and watched == self.window():
            self.cancel()
            return False
        if event.type() == QEvent.Type.MouseButtonPress and watched != self:
            self.cancel()
            return False
        if event.type() == QEvent.Type.ShortcutOverride:
            event.accept()
            return True
        if event.type() != QEvent.Type.KeyPress:
            return False
        key = event.key()
        if event.isAutoRepeat():
            return True
        if key == Qt.Key.Key_Escape:
            self.cancel()
            return True
        if key in (Qt.Key.Key_Control, Qt.Key.Key_Shift, Qt.Key.Key_Alt, Qt.Key.Key_Meta, Qt.Key.Key_AltGr):
            return True
        mods = event.modifiers()
        parts = [name for flag, name in ((Qt.KeyboardModifier.ControlModifier, "Ctrl"),
                                        (Qt.KeyboardModifier.AltModifier, "Alt"),
                                        (Qt.KeyboardModifier.ShiftModifier, "Shift"),
                                        (Qt.KeyboardModifier.MetaModifier, "Win")) if mods & flag]
        if Qt.Key.Key_F1 <= key <= Qt.Key.Key_F11:
            value = "F" + str(key - Qt.Key.Key_F1 + 1)
        elif Qt.Key.Key_A <= key <= Qt.Key.Key_Z or Qt.Key.Key_0 <= key <= Qt.Key.Key_9:
            value = chr(key)
        else:
            value = {Qt.Key.Key_Space: "Space", Qt.Key.Key_Tab: "Tab", Qt.Key.Key_Return: "Enter",
                     Qt.Key.Key_Enter: "Enter", Qt.Key.Key_Backspace: "Backspace", Qt.Key.Key_Delete: "Delete",
                     Qt.Key.Key_Insert: "Insert", Qt.Key.Key_Home: "Home", Qt.Key.Key_End: "End",
                     Qt.Key.Key_PageUp: "PageUp", Qt.Key.Key_PageDown: "PageDown",
                     Qt.Key.Key_Left: "Left", Qt.Key.Key_Right: "Right", Qt.Key.Key_Up: "Up", Qt.Key.Key_Down: "Down"}.get(key, "")
        shortcut = "+".join(parts + [value])
        try:
            parse_hotkey(shortcut)
        except ValueError:
            self.setText("请按 F1–F11 或组合键（点击取消）")
        else:
            self.cancel()
            self.set_shortcut(shortcut)
        return True
