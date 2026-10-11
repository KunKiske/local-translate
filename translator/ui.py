from dataclasses import replace
from pathlib import Path
import threading
import time

from PySide6.QtCore import Qt, QEvent, QObject, QThread, QTimer, Signal, Slot, QMimeData, QSize
from PySide6.QtGui import QColor, QCursor, QFont, QIcon, QPainter, QPixmap, QPalette
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QFileDialog, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QMenu, QMessageBox, QPlainTextEdit, QPushButton,
    QSystemTrayIcon, QVBoxLayout, QWidget, QListWidget, QListWidgetItem, QStackedWidget, QStyleFactory, QSpinBox,
)

from .config import Settings
from .engine import TranslationEngine, language_pair, validate_model
from .naming import STYLES, generate_names
from .dictionary import Dictionary
from .hotkey_edit import HotkeyButton
from . import native

STYLE = """
QWidget { font-family: 'Microsoft YaHei UI'; font-size: 13px; }
QWidget#popup, QDialog { background: #f5f7fb; }
QLabel#brand { font-size: 20px; font-weight: 700; color: #183b65; }
QLabel#muted { color: #718096; font-size: 12px; }
QLabel#status { color: #476584; font-size: 12px; }
QPlainTextEdit, QLineEdit { background: white; border: 1px solid #d9e1ec;
    border-radius: 8px; padding: 9px; selection-background-color: #0078d4; selection-color: white; }
QComboBox { min-height: 28px; }
QPlainTextEdit:focus, QLineEdit:focus { border: 1px solid #6499de; }
QPlainTextEdit#output { background: #eaf2fc; border: 1px solid #d1e2f7; }
QPushButton { background: #e6ecf4; border: none; border-radius: 7px; padding: 8px 13px; }
QPushButton:hover { background: #d6e3f3; }
QPushButton#primary { background: #2869bb; color: white; }
QPushButton#primary:hover { background: #205a9f; }
QPushButton:disabled { background: #dce2eb; color: #95a0af; }
QWidget#popup QLabel#brand { font-size: 18px; }
QWidget#popup QPushButton { padding: 6px 10px; }
QWidget#popup QPlainTextEdit { padding: 6px; }
QListWidget#names { background: #eaf2fc; border: 1px solid #d1e2f7; border-radius: 8px; padding: 4px; }
QListWidget#names::item { padding: 6px 8px; border-radius: 5px; }
QListWidget#names::item:hover { background: #d9e8fb; }
QListWidget#names::item:selected { background: #c9def8; color: #183b65; }
QListWidget#names QScrollBar:vertical { width: 8px; background: transparent; margin: 2px; }
QListWidget#names QScrollBar::handle:vertical { background: #a9c3e6; border-radius: 3px; min-height: 20px; }
QListWidget#names QScrollBar::add-line:vertical, QListWidget#names QScrollBar::sub-line:vertical { height: 0px; }
QListWidget#names QScrollBar::add-page:vertical, QListWidget#names QScrollBar::sub-page:vertical { background: transparent; }
QMenu { background: white; padding: 6px; }
QMenu::item { padding: 8px 22px; }
QMenu::item:selected { background: #eaf2fc; }
"""


def apply_appearance(app):
    """Use native Windows controls with one consistent light palette."""
    app.styleHints().setColorScheme(Qt.ColorScheme.Light)
    styles = {name.lower(): name for name in QStyleFactory.keys()}
    app.setStyle(styles.get("windowsvista", "Fusion"))
    palette = app.style().standardPalette()
    for role, color in (
        (QPalette.ColorRole.Window, "#f5f7fb"),
        (QPalette.ColorRole.WindowText, "#202020"),
        (QPalette.ColorRole.Base, "#ffffff"),
        (QPalette.ColorRole.AlternateBase, "#f4f4f4"),
        (QPalette.ColorRole.Text, "#202020"),
        (QPalette.ColorRole.Button, "#f0f0f0"),
        (QPalette.ColorRole.ButtonText, "#202020"),
        (QPalette.ColorRole.Highlight, "#0078d4"),
        (QPalette.ColorRole.HighlightedText, "#ffffff"),
        (QPalette.ColorRole.ToolTipBase, "#ffffff"),
        (QPalette.ColorRole.ToolTipText, "#202020"),
        (QPalette.ColorRole.PlaceholderText, "#808080"),
    ):
        palette.setColor(role, QColor(color))
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.WindowText, QPalette.ColorRole.ButtonText):
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor("#808080"))
    app.setPalette(palette)
    app.setStyleSheet(STYLE)


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
    HINT = "输入中文或 English，稍停片刻自动翻译…"

    def __init__(self):
        super().__init__()
        self.composing = False
        self.setPlaceholderText(self.HINT)

    def inputMethodEvent(self, event):
        if event.preeditString() or event.commitString():
            self.setPlaceholderText("")
        self.composing = bool(event.preeditString())
        super().inputMethodEvent(event)

    def keyPressEvent(self, event):
        self.setPlaceholderText("")
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
    candidate_chosen = Signal()

    def __init__(self):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setObjectName("popup")
        self.setWindowTitle("轻译 · 本地翻译")
        self.setWindowIcon(app_icon())
        self.resize(480, 360)
        self.mode = "translate"
        self.settings_open = False
        self.choice_by_mode = {"translate": "auto", "naming": "camel", "dictionary": "auto"}
        self.drag_origin = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)
        top = QHBoxLayout()
        brand = QLabel("轻译")
        brand.setObjectName("brand")
        top.addWidget(brand)
        hint = QLabel("LOCAL TRANSLATE")
        hint.setObjectName("muted")
        top.addWidget(hint)
        top.addStretch()
        self.settings_button = QPushButton("设置")
        self.settings_button.clicked.connect(self.settings_requested)
        top.addWidget(self.settings_button)
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
        self.direction.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        for label, value in (("自动识别 · 中英互译", "auto"), ("中文 → English", "zh-en"), ("English → 中文", "en-zh")):
            self.direction.addItem(label, value)
        self.direction.currentIndexChanged.connect(self.changed)
        mode_row.addWidget(self.direction)
        layout.addLayout(mode_row)
        self.source = InputEdit()
        self.source.setMinimumHeight(80)
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
        self.output.setMinimumHeight(80)
        self.candidates = QListWidget()
        self.candidates.setObjectName("names")
        self.candidates.setMinimumHeight(80)
        self.candidates.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.candidates.itemClicked.connect(lambda item: self.candidate_chosen.emit())
        self.candidates.installEventFilter(self)
        self.source.installEventFilter(self)
        self.results = QStackedWidget()
        self.results.addWidget(self.output)
        self.results.addWidget(self.candidates)
        layout.addWidget(self.results, 1)
        bottom = QHBoxLayout()
        self.footer = QLabel("关闭复制 · Enter 粘贴 · Shift+Enter 换行")
        self.footer.setObjectName("muted")
        bottom.addWidget(self.footer)
        bottom.addStretch()
        self.send = QPushButton("粘贴并关闭 ↵")
        self.send.setObjectName("primary")
        self.send.clicked.connect(self.submit)
        bottom.addWidget(self.send)
        layout.addLayout(bottom)

    def set_mode(self, mode):
        self.choice_by_mode[self.mode] = self.direction.currentData()
        self.mode = mode
        naming = mode == "naming"
        dictionary = mode == "dictionary"
        multiple = naming or dictionary
        self.mode_label.setText("离线字典" if dictionary else "代码命名" if naming else "中英翻译")
        self.setWindowTitle("轻译 · " + self.mode_label.text())
        self.direction.blockSignals(True)
        self.direction.clear()
        choices = (("中英双向 · 释义与词性", "auto"),) if dictionary else STYLES if naming else (("自动识别 · 中英互译", "auto"), ("中文 → English", "zh-en"), ("English → 中文", "en-zh"))
        for label, value in choices:
            self.direction.addItem(label, value)
        self.direction.setCurrentIndex(max(0, self.direction.findData(self.choice_by_mode[mode])))
        self.direction.blockSignals(False)
        self.direction.setEnabled(not dictionary)
        self.source.setMinimumHeight(60 if dictionary else 80)
        self.source.setMaximumHeight(72 if dictionary else 16777215)
        self.candidates.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff if dictionary else Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.results.setCurrentWidget(self.candidates if multiple else self.output)
        self.footer.setText("单击输出 · ↑↓ 选择 · Enter 确认" if multiple else "关闭复制 · Enter 粘贴 · Shift+Enter 换行")
        self.send.setText("输出选中 ↵" if multiple else "粘贴并关闭 ↵")
        self.layout().setStretchFactor(self.results, 2 if multiple else 1)
        self.resize(480, 400 if multiple else 360)

    def show_candidates(self, candidates):
        self.candidates.clear()
        for candidate in candidates:
            item = QListWidgetItem(candidate["name"] + "    · " + candidate["label"])
            item.setData(Qt.ItemDataRole.UserRole, candidate["name"])
            item.setToolTip(candidate["name"] + "\n单击：复制并粘贴回原输入位置")
            item.setSizeHint(QSize(self.candidates.fontMetrics().horizontalAdvance(item.text()) + 24, 32))
            self.candidates.addItem(item)
        if self.candidates.count():
            self.candidates.setCurrentRow(0)

    def show_definitions(self, candidates):
        self.candidates.clear()
        for candidate in candidates:
            title = candidate["name"]
            label = candidate["label"]
            detail = candidate["detail"]
            # Keep rows compact; full definitions remain available in the tooltip.
            text = title + "\n" + label + (" · " + detail if title not in detail else "")
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, title)
            item.setToolTip(label + (" /" + candidate["phonetic"] + "/" if candidate["phonetic"] else "") + "\n" + detail + "\n单击：输出 " + title)
            item.setSizeHint(QSize(0, 50))
            self.candidates.addItem(item)
        if self.candidates.count():
            self.candidates.setCurrentRow(0)

    def eventFilter(self, watched, event):
        if self.mode in ("naming", "dictionary") and event.type() == QEvent.Type.KeyPress:
            if watched == self.candidates and event.key() in (Qt.Key.Key_Enter, Qt.Key.Key_Return):
                self.submit.emit()
                return True
            if watched == self.source and not self.source.composing and self.candidates.count() and event.key() in (Qt.Key.Key_Up, Qt.Key.Key_Down):
                offset = 1 if event.key() == Qt.Key.Key_Down else -1
                self.candidates.setCurrentRow((self.candidates.currentRow() + offset) % self.candidates.count())
                return True
        return super().eventFilter(watched, event)

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
        if self.settings_open:
            return
        active_popup = QApplication.activePopupWidget()
        if self.direction.view().isVisible() or (active_popup and self.isAncestorOf(active_popup)):
            # Opening our combobox or context menu is not an outside click.
            QTimer.singleShot(100, self.close_if_inactive)
            return
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
        super().__init__(controller.popup)
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)
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
        self.hotkey = HotkeyButton(controller.settings.hotkey)
        form.addRow("翻译快捷键", self.hotkey)
        self.naming_hotkey = HotkeyButton(controller.settings.naming_hotkey)
        form.addRow("代码命名快捷键", self.naming_hotkey)
        self.dictionary_hotkey = HotkeyButton(controller.settings.dictionary_hotkey)
        form.addRow("字典快捷键", self.dictionary_hotkey)
        self.recorders = (self.hotkey, self.naming_hotkey, self.dictionary_hotkey)
        for recorder in self.recorders:
            recorder.started.connect(self.start_recording)
        self.finished.connect(self.cancel_recording)
        self.delay = QSpinBox()
        self.delay.setRange(100, 2000)
        self.delay.setSingleStep(50)
        self.delay.setSuffix(" ms")
        self.delay.setValue(controller.settings.debounce_ms)
        form.addRow("输入后等待", self.delay)
        layout.addLayout(form)
        note = QLabel("CPU 使用处理器，推荐 int8；CUDA 使用 NVIDIA 显卡，可选 float16。\n快捷键点击录制，再次点击或 Esc 取消；保存后生效。字典查询不依赖模型。")
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

    def start_recording(self, selected):
        for recorder in self.recorders:
            if recorder is not selected:
                recorder.cancel()

    def cancel_recording(self, *_):
        for recorder in self.recorders:
            recorder.cancel()

    def present(self):
        if not self.isVisible():
            self.adjustSize()
            anchor = self.controller.popup
            point = anchor.frameGeometry().center() if anchor.isVisible() else QCursor.pos()
            area = (QApplication.screenAt(point) or QApplication.primaryScreen()).availableGeometry()
            center = point if anchor.isVisible() else area.center()
            self.move(max(area.left(), min(center.x() - self.width() // 2, area.right() - self.width())),
                      max(area.top(), min(center.y() - self.height() // 2, area.bottom() - self.height())))
        self.showNormal()
        self.raise_()
        self.activateWindow()
        native.focus(int(self.winId()))

    def browse(self):
        path = QFileDialog.getExistingDirectory(self, "选择 NLLB 模型目录", self.path.text())
        if path:
            self.path.setText(path)

    def save(self):
        self.cancel_recording()
        settings = replace(self.controller.settings, model_path=self.path.text().strip(),
                           device=self.device.currentText(), compute_type=self.compute.currentText(),
                           hotkey=self.hotkey.shortcut, naming_hotkey=self.naming_hotkey.shortcut,
                           dictionary_hotkey=self.dictionary_hotkey.shortcut, debounce_ms=self.delay.value())
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
    finished = Signal(int, object, str)

    def __init__(self):
        super().__init__()
        self.engine = TranslationEngine()
        self.dictionary = Dictionary()

    @Slot(object)
    def run(self, job):
        ident, text, mode, direction, settings, cancel = job
        try:
            if text is None:
                self.engine.load(settings)
                result = ""
            elif mode == "naming":
                result = generate_names(self.engine, text, direction, settings, cancel.is_set)
            elif mode == "dictionary":
                result = self.dictionary.lookup(text, cancel.is_set)
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
        self.hotkeys_suspended = False
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
        self.popup.candidate_chosen.connect(self.submit)
        self.popup.dismissed.connect(self.dismissed)
        self.popup.settings_requested.connect(self.show_settings)
        self.tray = QSystemTrayIcon(app_icon(), self)
        self.tray.setToolTip(f"轻译 · {self.settings.hotkey} 翻译 / {self.settings.naming_hotkey} 命名 / {self.settings.dictionary_hotkey} 字典")
        menu = QMenu()
        menu.addAction("打开翻译窗口", self.open_input)
        menu.addAction("打开代码命名", lambda: self.open_input(mode="naming"))
        menu.addAction("打开字典", lambda: self.open_input(mode="dictionary"))
        menu.addAction("模型与快捷键设置", self.show_settings)
        menu.addSeparator()
        menu.addAction("退出轻译", self.quit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda reason: self.open_input() if reason == QSystemTrayIcon.ActivationReason.DoubleClick else None)
        self.menu = menu
        self.tray.show()
        if register_hotkeys:
            try:
                self.hotkeys.configure(self.settings.hotkey, self.settings.naming_hotkey, self.settings.dictionary_hotkey)
            except ValueError as exc:
                QTimer.singleShot(0, lambda message=str(exc): self.notify(message))
        self.preload()

    def notify(self, message):
        self.tray.showMessage("轻译", message, QSystemTrayIcon.MessageIcon.Information, 4000)

    def apply_settings(self, settings):
        previous = self.settings
        self.hotkeys.configure(settings.hotkey, settings.naming_hotkey, settings.dictionary_hotkey)
        try:
            settings.save()
        except OSError:
            self.hotkeys.configure(previous.hotkey, previous.naming_hotkey, previous.dictionary_hotkey)
            raise
        self.settings = settings
        self.tray.setToolTip(f"轻译 · {settings.hotkey} 翻译 / {settings.naming_hotkey} 命名 / {settings.dictionary_hotkey} 字典")
        self.preload()

    def preload(self):
        self.revision += 1
        self.enqueue(None)

    def show_settings(self):
        self.capture_revision += 1
        self.capturing = False
        self.submit_pending = False
        self.timer.stop()
        self.popup.settings_open = True
        if self.dialog and self.dialog.isVisible():
            self.dialog.present()
            return
        if self.dialog:
            self.dialog.deleteLater()
        # The existing global bindings must reach Qt while recording (including F1/F2/F3).
        self.hotkeys_suspended = bool(self.hotkeys.keys)
        if self.hotkeys_suspended:
            self.hotkeys.unregister()
        self.dialog = SettingsDialog(self)
        self.dialog.finished.connect(self.settings_closed)
        self.dialog.present()

    def settings_closed(self, result):
        self.popup.settings_open = False
        if self.hotkeys_suspended and not self.quitting and not self.hotkeys.keys:
            try:
                self.hotkeys.configure(self.settings.hotkey, self.settings.naming_hotkey, self.settings.dictionary_hotkey)
            except ValueError as exc:
                self.notify(str(exc))
        self.hotkeys_suspended = False
        if self.popup.isVisible() and not self.quitting:
            self.popup.raise_()
            self.popup.activateWindow()
            native.focus(int(self.popup.winId()))
            self.popup.source.setFocus()
            if self.result_revision != self.revision and self.popup.source.toPlainText().strip():
                self.edited()

    def on_hotkey(self, ident):
        if ident not in (1, 2, 3) or self.quitting or (self.dialog and self.dialog.isVisible()):
            return
        mode = {1: "translate", 2: "naming", 3: "dictionary"}[ident]
        if self.popup.isVisible():
            if self.popup.mode != mode:
                self.start_popup(self.popup.source.toPlainText(), mode)
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
            self.capture_selection(target, mode)
        released()

    def open_input(self, target=None, mode="translate"):
        if self.quitting:
            return
        self.capture_revision += 1
        self.capturing = False
        self.target = target or native.foreground()
        self.start_popup("", mode)

    def start_popup(self, text, mode="translate"):
        self.popup.set_mode(mode)
        hint = "输入中文或英文单词、短语，查看释义与词性…" if mode == "dictionary" else "描述一个用途，例如：玩家移动速度；稍停生成候选…" if mode == "naming" else InputEdit.HINT
        self.popup.source.setPlaceholderText(hint if not text else "")
        self.popup.source.blockSignals(True)
        self.popup.source.setPlainText(text)
        self.popup.source.blockSignals(False)
        self.edited()
        self.popup.present()
        if text:
            self.timer.stop()
            self.translate()

    def capture_selection(self, target, mode="translate"):
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
            self.start_popup("", mode)
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
                self.start_popup(text, mode)
            elif time.monotonic() >= deadline:
                self.capturing = False
                self.target = target
                self.start_popup("", mode)
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
        self.popup.candidates.clear()
        text = self.popup.source.toPlainText().strip()
        self.popup.send.setEnabled(bool(text))
        self.timer.stop()
        if text:
            self.popup.status.setText("等待输入完成…")
            self.timer.start(min(200, self.settings.debounce_ms) if self.popup.mode == "dictionary" else self.settings.debounce_ms)
        else:
            self.popup.status.setText("ECDICT 离线词典 · 中文查英文 / 英文查释义" if self.popup.mode == "dictionary" else "一个需求 → 多个候选 · 点击名字输出" if self.popup.mode == "naming" else "本地处理 · 文本不会上传")

    def translate(self):
        text = self.popup.source.toPlainText().strip()
        if not text:
            return
        activity = "正在查询离线词典…" if self.popup.mode == "dictionary" else "正在生成候选名称…" if self.popup.mode == "naming" else "正在本地翻译…"
        self.popup.status.setText(activity + (" 完成后将自动粘贴。" if self.submit_pending else ""))
        self.enqueue(text)

    def enqueue(self, text):
        self.cancel.set()
        job = (self.revision, text, self.popup.mode, self.popup.direction.currentData(), replace(self.settings), threading.Event())
        if self.busy:
            self.pending = job
        else:
            self.dispatch(job)

    def dispatch(self, job):
        self.busy = True
        self.active_job = job
        self.cancel = job[-1]
        self.work.emit(job)

    @Slot(int, object, str)
    def completed(self, ident, result, error):
        self.busy = False
        was_preload = self.active_job[1] is None
        if self.quitting:
            self.finish_quit()
            return
        if ident == self.revision:
            if error:
                self.submit_pending = False
                self.popup.status.setText(("查询失败：" if self.popup.mode == "dictionary" else "生成失败：" if self.popup.mode == "naming" else "翻译失败：") + error)
                if was_preload:
                    self.notify("模型加载失败：" + error)
            elif was_preload:
                self.notify(f"本地模型已就绪。{self.settings.hotkey} 翻译，{self.settings.naming_hotkey} 代码命名，{self.settings.dictionary_hotkey} 字典；支持取词或输入。")
            elif self.popup.isVisible():
                self.result_revision = ident
                if self.popup.mode == "dictionary":
                    self.popup.show_definitions(result)
                    self.popup.send.setEnabled(bool(result))
                    self.popup.status.setText(f"ECDICT · 显示 {len(result)} 项 · 单击输出所选词义" if result else "词典未收录；请尝试词语原形或改用翻译模式。")
                    if not result:
                        self.submit_pending = False
                elif self.popup.mode == "naming":
                    self.popup.show_candidates(result)
                    self.popup.status.setText(f"生成 {len(result)} 个候选 · 单击名字粘贴并关闭")
                else:
                    self.popup.output.setPlainText(result)
                    src, _ = language_pair(self.popup.source.toPlainText(), self.popup.direction.currentData())
                    self.popup.status.setText(("中文 → English" if src == "zho_Hans" else "English → 中文") + " · 翻译完成 · 关闭窗口自动复制")
                if self.submit_pending:
                    self.submit()
        if self.pending:
            job, self.pending = self.pending, None
            self.dispatch(job)

    def current_result(self):
        if self.result_revision != self.revision:
            return ""
        if self.popup.mode in ("naming", "dictionary"):
            item = self.popup.candidates.currentItem()
            return item.data(Qt.ItemDataRole.UserRole) if item else ""
        return self.popup.output.toPlainText().strip()

    def dismissed(self):
        result = self.current_result()
        if result:
            self.app.clipboard().setText(result)
        elif self.popup.source.toPlainText().strip() and not self.quitting:
            self.notify("窗口已关闭，当前结果尚未完成，剪贴板保持原样。")
        self.revision += 1
        self.cancel.set()
        self.pending = None
        self.submit_pending = False
        self.timer.stop()

    def submit(self):
        result = self.current_result()
        if not result:
            if self.popup.mode == "dictionary" and self.result_revision == self.revision:
                return
            if self.popup.source.toPlainText().strip():
                self.submit_pending = True
                self.timer.stop()
                # Do not requeue an identical in-flight request on repeated Enter.
                if not self.busy or self.active_job[0] != self.revision:
                    self.translate()
                self.popup.status.setText("正在查询，完成后将输出首个词义并关闭…" if self.popup.mode == "dictionary" else "正在生成，完成后将输出首个候选并关闭…" if self.popup.mode == "naming" else "正在翻译，完成后将自动粘贴并关闭…")
            return
        target = self.target
        self.popup.close()
        if not target or target == int(self.popup.winId()) or not native.focus(target):
            self.notify("内容已复制，请在目标输入框按 Ctrl+V 粘贴。")
            return
        deadline = time.monotonic() + 1.0
        def paste():
            if native.foreground() != target:
                self.notify("目标窗口已改变。内容已复制，请手动 Ctrl+V。")
                return
            if native.modifiers_pressed() or native.user32.GetAsyncKeyState(0x0D) & 0x8000:
                if time.monotonic() < deadline:
                    QTimer.singleShot(25, paste)
                else:
                    self.notify("内容已复制，请松开按键后 Ctrl+V。")
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
