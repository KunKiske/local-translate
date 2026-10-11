from dataclasses import replace
from pathlib import Path
import threading
import time

from PySide6.QtCore import Qt, QEvent, QObject, QThread, QTimer, Signal, Slot, QMimeData
from PySide6.QtGui import QColor, QCursor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QFileDialog, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QMenu, QMessageBox, QPlainTextEdit, QPushButton,
    QSystemTrayIcon, QVBoxLayout, QWidget,
)

from .config import Settings
from .engine import TranslationEngine, language_pair, validate_model
from . import native

STYLE = """
QWidget { font-family: 'Microsoft YaHei UI'; font-size: 13px; color: #23324b; }
QWidget#popup, QDialog { background: #f5f7fb; }
QLabel#brand { font-size: 20px; font-weight: 700; color: #183b65; }
QLabel#muted { color: #718096; font-size: 12px; }
QLabel#status { color: #476584; font-size: 12px; }
QPlainTextEdit, QLineEdit, QComboBox { background: white; border: 1px solid #d9e1ec;
    border-radius: 8px; padding: 9px; selection-background-color: #c3dcfb; }
QPlainTextEdit:focus, QLineEdit:focus { border: 1px solid #6499de; }
QPlainTextEdit#output { background: #eaf2fc; border: 1px solid #d1e2f7; }
QPushButton { background: #e6ecf4; border: none; border-radius: 7px; padding: 8px 13px; }
QPushButton:hover { background: #d6e3f3; }
QPushButton#primary { background: #2869bb; color: white; }
QPushButton#primary:hover { background: #205a9f; }
QPushButton:disabled { background: #dce2eb; color: #95a0af; }
QMenu { background: white; padding: 6px; }
QMenu::item { padding: 8px 22px; }
QMenu::item:selected { background: #eaf2fc; }
"""


def app_icon():
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor("#2869bb"))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(2, 2, 60, 60, 16, 16)
    painter.setPen(QColor("white"))
    painter.setFont(QFont("Microsoft YaHei UI", 25, QFont.Weight.Bold))
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "译")
    painter.end()
    return QIcon(pixmap)


class InputEdit(QPlainTextEdit):
    submit = Signal()

    def __init__(self):
        super().__init__()
        self.composing = False

    def inputMethodEvent(self, event):
        self.composing = bool(event.preeditString())
        super().inputMethodEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            if not self.composing:
                self.submit.emit()
                event.accept()
                return
        super().keyPressEvent(event)


class Popup(QWidget):
    changed = Signal()
    submit = Signal()
    dismissed = Signal()
    settings_requested = Signal()

    def __init__(self):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setObjectName("popup")
        self.setWindowTitle("轻译 · 本地翻译")
        self.setWindowIcon(app_icon())
        self.resize(580, 475)
        self.drag_origin = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 18)
        layout.setSpacing(12)
        top = QHBoxLayout()
        brand = QLabel("轻译")
        brand.setObjectName("brand")
        top.addWidget(brand)
        hint = QLabel("LOCAL TRANSLATE")
        hint.setObjectName("muted")
        top.addWidget(hint)
        top.addStretch()
        settings = QPushButton("设置")
        settings.clicked.connect(self.settings_requested)
        top.addWidget(settings)
        close = QPushButton("×")
        close.setFixedWidth(34)
        close.clicked.connect(self.close)
        top.addWidget(close)
        layout.addLayout(top)
        mode_row = QHBoxLayout()
        self.mode_label = QLabel("中英翻译")
        mode_row.addWidget(self.mode_label)
        mode_row.addStretch()
        self.direction = QComboBox()
        for label, value in (("自动识别 · 中英互译", "auto"), ("中文 → English", "zh-en"), ("English → 中文", "en-zh")):
            self.direction.addItem(label, value)
        self.direction.currentIndexChanged.connect(self.changed)
        mode_row.addWidget(self.direction)
        layout.addLayout(mode_row)
        self.source = InputEdit()
        self.source.setPlaceholderText("输入中文或 English，稍停片刻自动翻译…")
        self.source.setMinimumHeight(115)
        self.source.textChanged.connect(self.changed)
        self.source.submit.connect(self.submit)
        layout.addWidget(self.source, 1)
        self.status = QLabel("本地处理 · 文本不会上传")
        self.status.setObjectName("status")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.output = QPlainTextEdit()
        self.output.setObjectName("output")
        self.output.setReadOnly(True)
        self.output.setPlaceholderText("译文将显示在这里")
        self.output.setMinimumHeight(115)
        layout.addWidget(self.output, 1)
        bottom = QHBoxLayout()
        footer = QLabel("关闭即复制 · Enter 粘贴 · Shift+Enter 换行")
        footer.setObjectName("muted")
        bottom.addWidget(footer)
        bottom.addStretch()
        self.send = QPushButton("粘贴并关闭 ↵")
        self.send.setObjectName("primary")
        self.send.clicked.connect(self.submit)
        bottom.addWidget(self.send)
        layout.addLayout(bottom)

    def present(self):
        point = QCursor.pos()
        screen = QApplication.screenAt(point) or QApplication.primaryScreen()
        area = screen.availableGeometry()
        self.move(max(area.left(), min(point.x() + 16, area.right() - self.width())),
                  max(area.top(), min(point.y() + 20, area.bottom() - self.height())))
        self.show()
        self.raise_()
        self.activateWindow()
        native.focus(int(self.winId()))
        self.source.setFocus()

    def event(self, event):
        if event.type() == QEvent.Type.WindowDeactivate and self.isVisible():
            QTimer.singleShot(100, self.close_if_inactive)
        return super().event(event)

    def close_if_inactive(self):
        if self.isVisible() and not self.isActiveWindow():
            self.close()

    def closeEvent(self, event):
        self.dismissed.emit()
        event.accept()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()
        elif event.key() in (Qt.Key.Key_Enter, Qt.Key.Key_Return):
            self.submit.emit()
        else:
            super().keyPressEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and event.position().y() < 65:
            self.drag_origin = event.globalPosition().toPoint() - self.pos()

    def mouseMoveEvent(self, event):
        if self.drag_origin is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self.drag_origin)

    def mouseReleaseEvent(self, event):
        self.drag_origin = None


class SettingsDialog(QDialog):
    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        self.setWindowTitle("轻译 · 设置")
        self.setWindowIcon(app_icon())
        self.setMinimumWidth(620)
        layout = QVBoxLayout(self)
        intro = QLabel("本地模型与快捷键")
        intro.setObjectName("brand")
        layout.addWidget(intro)
        description = QLabel("支持 CTranslate2 格式的 NLLB 模型（600M / 1.3B 等）。\n选择包含 model.bin、config.json、tokenizer.json 的文件夹。")
        description.setWordWrap(True)
        layout.addWidget(description)
        form = QFormLayout()
        model_row = QHBoxLayout()
        self.path = QLineEdit(controller.settings.model_path)
        model_row.addWidget(self.path)
        browse = QPushButton("浏览…")
        browse.clicked.connect(self.browse)
        model_row.addWidget(browse)
        form.addRow("模型目录", model_row)
        self.device = QComboBox()
        self.device.addItems(["cpu", "cuda"])
        self.device.setCurrentText(controller.settings.device)
        form.addRow("运行设备", self.device)
        self.compute = QComboBox()
        self.compute.addItems(["int8", "auto", "float32", "float16", "int8_float16"])
        self.compute.setCurrentText(controller.settings.compute_type)
        form.addRow("计算精度", self.compute)
        self.hotkey = QLineEdit(controller.settings.hotkey)
        form.addRow("唤起翻译窗口", self.hotkey)
        layout.addLayout(form)
        note = QLabel("推荐 CPU + int8；CUDA 需要兼容的 NVIDIA 驱动及 CUDA 运行库。\n快捷键支持 F1–F11、Ctrl+Alt+T 等组合。保存后自动加载验证模型。")
        note.setWordWrap(True)
        note.setObjectName("muted")
        layout.addWidget(note)
        self.message = QLabel("")
        self.message.setWordWrap(True)
        layout.addWidget(self.message)
        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)
        save = QPushButton("保存并应用")
        save.setObjectName("primary")
        save.clicked.connect(self.save)
        buttons.addWidget(save)
        layout.addLayout(buttons)

    def browse(self):
        path = QFileDialog.getExistingDirectory(self, "选择 NLLB 模型目录", self.path.text())
        if path:
            self.path.setText(path)

    def save(self):
        settings = replace(self.controller.settings, model_path=self.path.text().strip(),
                           device=self.device.currentText(), compute_type=self.compute.currentText(),
                           hotkey=self.hotkey.text().strip())
        try:
            validate_model(settings.model_path)
            if settings.device == "cpu" and settings.compute_type in ("float16", "int8_float16"):
                raise ValueError("CPU 请使用 int8、auto 或 float32。")
            self.controller.apply_settings(settings)
        except Exception as exc:
            self.message.setText(str(exc))
            return
        self.accept()


class Worker(QObject):
    finished = Signal(int, str, str)

    def __init__(self):
        super().__init__()
        self.engine = TranslationEngine()

    @Slot(object)
    def run(self, job):
        ident, text, direction, settings, cancel = job
        try:
            if text is None:
                self.engine.load(settings)
                result = ""
            else:
                result = self.engine.translate(text, direction, settings, cancel.is_set)
            self.finished.emit(ident, result, "")
        except Exception as exc:
            self.finished.emit(ident, "", str(exc))


class Controller(QObject):
    work = Signal(object)

    def __init__(self, app, register_hotkeys=True):
        super().__init__()
        self.app = app
        self.settings = Settings.load()
        self.popup = Popup()
        self.target = None
        self.revision = 0
        self.result_revision = -1
        self.submit_pending = False
        self.busy = False
        self.pending = None
        self.cancel = threading.Event()
        self.quitting = False
        self.capturing = False
        self.capture_revision = 0
        self.dialog = None
        self.hotkeys = native.Hotkeys(self.on_hotkey)
        app.installNativeEventFilter(self.hotkeys)
        self.thread = QThread()
        self.worker = Worker()
        self.worker.moveToThread(self.thread)
        self.work.connect(self.worker.run)
        self.worker.finished.connect(self.completed)
        self.thread.finished.connect(self.worker.deleteLater)
        self.thread.start()
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.translate)
        self.popup.changed.connect(self.edited)
        self.popup.submit.connect(self.submit)
        self.popup.dismissed.connect(self.dismissed)
        self.popup.settings_requested.connect(self.show_settings)
        self.tray = QSystemTrayIcon(app_icon(), self)
        self.tray.setToolTip(f"轻译 · {self.settings.hotkey} 翻译（选词或输入）")
        menu = QMenu()
        menu.addAction("打开翻译窗口", self.open_input)
        menu.addAction("模型与快捷键设置", self.show_settings)
        menu.addSeparator()
        menu.addAction("退出轻译", self.quit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda reason: self.open_input() if reason == QSystemTrayIcon.ActivationReason.DoubleClick else None)
        self.menu = menu
        self.tray.show()
        if register_hotkeys:
            try:
                self.hotkeys.configure(self.settings.hotkey)
            except ValueError as exc:
                QTimer.singleShot(0, lambda message=str(exc): self.notify(message))
        self.preload()

    def notify(self, message):
        self.tray.showMessage("轻译", message, QSystemTrayIcon.MessageIcon.Information, 4000)

    def apply_settings(self, settings):
        previous = self.settings
        self.hotkeys.configure(settings.hotkey)
        try:
            settings.save()
        except OSError:
            self.hotkeys.configure(previous.hotkey)
            raise
        self.settings = settings
        self.tray.setToolTip(f"轻译 · {settings.hotkey} 翻译（选词或输入）")
        self.preload()

    def preload(self):
        self.revision += 1
        self.enqueue(None)

    def show_settings(self):
        self.popup.close()
        if self.dialog and self.dialog.isVisible():
            self.dialog.raise_()
            self.dialog.activateWindow()
            return
        self.dialog = SettingsDialog(self)
        self.dialog.show()
        self.dialog.activateWindow()

    def on_hotkey(self, ident):
        if ident != 1 or self.quitting or (self.dialog and self.dialog.isVisible()):
            return
        if self.popup.isVisible():
            self.popup.source.setFocus()
            return
        target = native.foreground()
        deadline = time.monotonic() + 1.5
        def released():
            if native.foreground() != target:
                return
            if native.modifiers_pressed():
                if time.monotonic() < deadline:
                    QTimer.singleShot(30, released)
                return
            self.capture_selection(target)
        released()

    def open_input(self, target=None):
        if self.quitting:
            return
        self.capture_revision += 1
        self.capturing = False
        self.target = target or native.foreground()
        self.start_popup("")

    def start_popup(self, text):
        self.popup.source.blockSignals(True)
        self.popup.source.setPlainText(text)
        self.popup.source.blockSignals(False)
        self.edited()
        self.popup.present()
        if text:
            self.timer.stop()
            self.translate()

    def capture_selection(self, target):
        if self.capturing:
            return
        self.capturing = True
        self.capture_revision += 1
        capture_id = self.capture_revision
        clipboard = self.app.clipboard()
        original = QMimeData()
        current = clipboard.mimeData()
        if current:
            for fmt in current.formats():
                original.setData(fmt, current.data(fmt))
        sequence = native.user32.GetClipboardSequenceNumber()
        try:
            native.shortcut("C")
        except Exception as exc:
            self.capturing = False
            self.target = target
            self.start_popup("")
            self.popup.status.setText("可以直接输入文字。取词未完成：" + str(exc))
            return
        deadline = time.monotonic() + 0.4
        def poll():
            if capture_id != self.capture_revision or self.quitting:
                return
            if native.foreground() != target:
                self.capturing = False
                return
            if native.user32.GetClipboardSequenceNumber() != sequence:
                text = clipboard.text().strip()
                clipboard.setMimeData(original)
                self.capturing = False
                self.target = target
                self.start_popup(text)
            elif time.monotonic() >= deadline:
                self.capturing = False
                self.target = target
                self.start_popup("")
            else:
                QTimer.singleShot(25, poll)
        QTimer.singleShot(40, poll)

    def edited(self):
        self.revision += 1
        self.cancel.set()
        self.pending = None
        self.submit_pending = False
        self.result_revision = -1
        self.popup.output.clear()
        text = self.popup.source.toPlainText().strip()
        self.popup.send.setEnabled(bool(text))
        self.timer.stop()
        if text:
            self.popup.status.setText("等待输入完成…")
            self.timer.start(self.settings.debounce_ms)
        else:
            self.popup.status.setText("本地处理 · 文本不会上传")

    def translate(self):
        text = self.popup.source.toPlainText().strip()
        if not text:
            return
        self.popup.status.setText("正在本地翻译…" + (" 完成后将自动粘贴。" if self.submit_pending else ""))
        self.enqueue(text)

    def enqueue(self, text):
        self.cancel.set()
        job = (self.revision, text, self.popup.direction.currentData(), replace(self.settings), threading.Event())
        if self.busy:
            self.pending = job
        else:
            self.dispatch(job)

    def dispatch(self, job):
        self.busy = True
        self.active_job = job
        self.cancel = job[-1]
        self.work.emit(job)

    @Slot(int, str, str)
    def completed(self, ident, result, error):
        self.busy = False
        was_preload = self.active_job[1] is None
        if self.quitting:
            self.finish_quit()
            return
        if ident == self.revision:
            if error:
                self.submit_pending = False
                self.popup.status.setText("翻译失败：" + error)
                if was_preload:
                    self.notify("模型加载失败：" + error)
            elif was_preload:
                self.notify("本地模型已就绪。按 " + self.settings.hotkey + " 打开翻译，有选中文字时自动填入，否则直接输入。")
            elif self.popup.isVisible():
                self.popup.output.setPlainText(result)
                self.result_revision = ident
                src, _ = language_pair(self.popup.source.toPlainText(), self.popup.direction.currentData())
                self.popup.status.setText(("中文 → English" if src == "zho_Hans" else "English → 中文") + " · 翻译完成 · 关闭窗口自动复制")
                if self.submit_pending:
                    self.submit()
        if self.pending:
            job, self.pending = self.pending, None
            self.dispatch(job)

    def current_result(self):
        return self.popup.output.toPlainText().strip() if self.result_revision == self.revision else ""

    def dismissed(self):
        result = self.current_result()
        if result:
            self.app.clipboard().setText(result)
        elif self.popup.source.toPlainText().strip() and not self.quitting:
            self.notify("窗口已关闭，当前译文尚未完成，剪贴板保持原样。")
        self.revision += 1
        self.cancel.set()
        self.pending = None
        self.submit_pending = False
        self.timer.stop()

    def submit(self):
        result = self.current_result()
        if not result:
            if self.popup.source.toPlainText().strip():
                self.submit_pending = True
                self.timer.stop()
                # Do not requeue an identical in-flight request on repeated Enter.
                if not self.busy or self.active_job[0] != self.revision:
                    self.translate()
                self.popup.status.setText("正在翻译，完成后将自动粘贴并关闭…")
            return
        target = self.target
        self.popup.close()
        if not target or target == int(self.popup.winId()) or not native.focus(target):
            self.notify("译文已复制，请在目标输入框按 Ctrl+V 粘贴。")
            return
        deadline = time.monotonic() + 1.0
        def paste():
            if native.foreground() != target:
                self.notify("目标窗口已改变。译文已复制，请手动 Ctrl+V。")
                return
            if native.modifiers_pressed() or native.user32.GetAsyncKeyState(0x0D) & 0x8000:
                if time.monotonic() < deadline:
                    QTimer.singleShot(25, paste)
                else:
                    self.notify("译文已复制，请松开按键后 Ctrl+V。")
                return
            try:
                native.shortcut("V")
            except Exception as exc:
                self.notify(str(exc))
        QTimer.singleShot(120, paste)

    def quit(self):
        self.quitting = True
        self.hotkeys.unregister()
        self.popup.close()
        if self.dialog:
            self.dialog.close()
        self.pending = None
        self.cancel.set()
        if self.busy:
            self.notify("正在结束当前翻译，随后退出…")
        else:
            self.finish_quit()

    def finish_quit(self):
        self.thread.quit()
        self.thread.wait()
        self.tray.hide()
        self.app.quit()
