"""Opt-in selection translation with a non-activating, read-only label."""
import time

from PySide6.QtCore import QObject, QPoint, Qt, QTimer, QMimeData
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget

from . import native


class ReadingTip(QWidget):
    def __init__(self):
        super().__init__(None, Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint |
                         Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setObjectName("readingTip")
        self.setStyleSheet("#readingTip { background: #f4f8fe; border: 1px solid #b9cfe9; border-radius: 7px; }"
                           "QLabel { border: none; background: transparent; color: #183b65; }"
                           "QLabel#readingTitle { color: #718096; font-size: 11px; }")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 10)
        layout.setSpacing(4)
        self.title = QLabel("阅读模式")
        self.title.setObjectName("readingTitle")
        layout.addWidget(self.title)
        self.text = QLabel()
        self.text.setTextFormat(Qt.TextFormat.PlainText)
        self.text.setWordWrap(True)
        layout.addWidget(self.text)

    def present(self, text, anchor, title="阅读模式"):
        self.title.setText(title)
        preview = " ".join(text.split())
        display = preview if len(preview) <= 240 else preview[:240] + "…"
        width = max(160, self.title.sizeHint().width(), min(296, self.text.fontMetrics().horizontalAdvance(display)))
        self.text.setFixedWidth(width)
        self.text.setText(display)
        self.setToolTip(text if display != text else "")
        self.adjustSize()
        screen = QApplication.screenAt(anchor) or QApplication.primaryScreen()
        area = screen.availableGeometry()
        x = min(anchor.x() + 12, area.right() - self.width())
        y = anchor.y() + 20
        if y + self.height() > area.bottom():
            y = anchor.y() - self.height() - 12
        self.move(max(area.left(), x), max(area.top(), y))
        self.show()  # Deliberately no activateWindow(), raise_(), or SetForegroundWindow().


class ReadingMode(QObject):
    def __init__(self, controller):
        super().__init__(controller)
        self.controller = controller
        self.enabled = False
        self.tip = ReadingTip()
        self.mouse = native.MouseObserver(self)
        self.mouse.activity.connect(self.mouse_event, Qt.ConnectionType.QueuedConnection)
        self.generation = 0
        self.press = None
        self.last_click = None
        self.target = None
        self.anchor = QPoint()
        self.capturing = False
        self.local = False
        self.local_text = ""
        self.focus_timer = QTimer(self)
        self.focus_timer.setInterval(100)
        self.focus_timer.timeout.connect(self.check_focus)

    def set_enabled(self, enabled):
        if enabled == self.enabled:
            return
        if enabled:
            self.mouse.start()
            self.enabled = True
            self.focus_timer.start()
        else:
            self.enabled = False
            self.mouse.stop()
            self.focus_timer.stop()
            self.dismiss()
        self.press = self.last_click = None

    def dismiss(self):
        self.generation += 1
        self.tip.hide()
        self.controller.cancel_reading()
        self.local = False
        self.local_text = ""

    def local_selection_changed(self):
        if self.local:
            self.dismiss()

    def translate_local(self, text, anchor):
        self.dismiss()
        text = text.strip()
        c = self.controller
        if not text or not c.popup.isVisible() or c.popup.settings_open:
            return
        self.local = True
        self.local_text = text
        self.target = int(c.popup.winId())
        self.anchor = QPoint(anchor)
        self.tip.present("正在翻译…", self.anchor, "划词翻译")
        self.focus_timer.start()
        c.enqueue_reading(self.generation, text)

    def context_valid(self):
        if self.local:
            c = self.controller
            return (not c.quitting and c.popup.isVisible() and not c.popup.settings_open
                    and c.popup.source.textCursor().selectedText().replace('\u2029', '\n').strip() == self.local_text)
        return self.available()

    def available(self):
        c = self.controller
        return (self.enabled and not c.quitting and not c.popup.isVisible()
                and not (c.dialog and c.dialog.isVisible()) and not QApplication.activePopupWidget())

    def check_focus(self):
        if self.tip.isVisible() and (not self.context_valid() or native.foreground() != self.target):
            self.dismiss()
        if not self.enabled and not self.tip.isVisible():
            self.focus_timer.stop()

    def mouse_event(self, message, x, y):
        if not self.enabled:
            return
        if message != 0x202:
            over_tip = self.tip.isVisible() and self.tip.geometry().contains(QCursor.pos())
            self.dismiss()
            self.press = None
            if message == 0x201 and not over_tip and self.available():
                now = time.monotonic()
                target = native.foreground()
                double = bool(self.last_click and target == self.last_click[3]
                              and now - self.last_click[0] <= native.user32.GetDoubleClickTime() / 1000
                              and abs(x - self.last_click[1]) <= 5 and abs(y - self.last_click[2]) <= 5)
                self.press = (x, y, target, double)
                self.last_click = (now, x, y, target)
            else:
                self.last_click = None
            return
        if not self.press:
            return
        px, py, target, double = self.press
        self.press = None
        if not self.available() or native.foreground() != target:
            return
        if not double and abs(x - px) + abs(y - py) < 5:
            return
        self.target = target
        self.anchor = QCursor.pos()
        token = self.generation
        deadline = time.monotonic() + .5

        def ready():
            if token != self.generation or not self.available() or native.foreground() != target:
                return
            if self.capturing or native.modifiers_pressed():
                if time.monotonic() < deadline:
                    QTimer.singleShot(20, ready)
                return
            self.capture(token, target)
        # Let the receiving application finish handling mouse-up and selecting text.
        QTimer.singleShot(35, ready)

    def capture(self, token, target):
        clipboard = self.controller.app.clipboard()
        original = QMimeData()
        current = clipboard.mimeData()
        if current:
            for fmt in current.formats():
                original.setData(fmt, current.data(fmt))
        sequence = native.user32.GetClipboardSequenceNumber()
        try:
            native.shortcut("C")
        except Exception as exc:
            self.tip.present(str(exc), self.anchor, "阅读模式 · 无法取词")
            return
        self.capturing = True
        deadline = time.monotonic() + .25

        def poll():
            if native.foreground() != target:
                self.capturing = False
                return
            if native.user32.GetClipboardSequenceNumber() != sequence:
                text = clipboard.text().strip()
                clipboard.setMimeData(original)
                self.capturing = False
                if text and token == self.generation and self.available():
                    self.tip.present("正在翻译…", self.anchor)
                    self.controller.enqueue_reading(token, text)
            elif time.monotonic() >= deadline:
                self.capturing = False
            else:
                QTimer.singleShot(10, poll)
        QTimer.singleShot(10, poll)

    def completed(self, token, text, error):
        if token != self.generation or not self.context_valid() or native.foreground() != self.target:
            return
        title = "划词翻译" if self.local else "阅读模式"
        self.tip.present(error or text, self.anchor, title + (" · 翻译失败" if error else " · 自动中英互译"))

    def stop(self):
        self.set_enabled(False)
        self.focus_timer.stop()
        self.dismiss()
        self.tip.hide()
