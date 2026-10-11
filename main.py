import argparse
import logging
import os
import sys

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")


def main():
    # Import native inference libraries before Qt installs its import introspection hook.
    import ctranslate2
    import tokenizers
    from PySide6.QtCore import QLockFile, QTimer
    from PySide6.QtWidgets import QApplication, QMessageBox
    from translator.config import APP_DIR
    from translator.ui import Controller, STYLE, app_icon

    parser = argparse.ArgumentParser()
    parser.add_argument("--settings", action="store_true")
    parser.add_argument("--smoke-test", action="store_true", help="Verify packaged inference and exit")
    args = parser.parse_args()
    APP_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=str(APP_DIR / "app.log"), level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s", encoding="utf-8")
    app = QApplication(sys.argv)
    app.setApplicationName("LocalTranslate")
    app.setQuitOnLastWindowClosed(False)
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    app.setWindowIcon(app_icon())
    if args.smoke_test:
        from translator.config import Settings
        from translator.engine import TranslationEngine
        try:
            engine = TranslationEngine()
            result = engine.translate("你好，很高兴见到你。", "auto", Settings.load())
            assert result and result.isascii(), result
            result2 = engine.translate("Good morning.", "auto", Settings.load())
            assert any('\u4e00' <= ch <= '\u9fff' for ch in result2), result2
            (APP_DIR / "smoke-test.txt").write_text(result + "\n" + result2, encoding="utf-8")
            return 0
        except Exception:
            logging.exception("Packaged smoke test failed")
            return 1
    lock = QLockFile(str(APP_DIR / "app.lock"))
    if not lock.tryLock(100):
        from translator.config import Settings
        QMessageBox.information(None, "轻译已在运行", "请按 " + Settings.load().hotkey + " 打开翻译，或右键系统托盘中的“译”图标打开设置。")
        return 0
    controller = Controller(app)
    def exception_hook(exc_type, value, traceback):
        logging.error("Unhandled exception", exc_info=(exc_type, value, traceback))
        controller.notify("出现错误：" + str(value))
    sys.excepthook = exception_hook
    if args.settings or not os.path.isfile(os.path.join(controller.settings.model_path, "model.bin")):
        QTimer.singleShot(0, controller.show_settings)
    code = app.exec()
    lock.unlock()
    return code


if __name__ == "__main__":
    raise SystemExit(main())
