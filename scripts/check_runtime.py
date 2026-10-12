"""Console checks used by install.cmd; no model or user configuration is changed."""
import struct
import sys


def main():
    if sys.version_info[:2] != (3, 11) or struct.calcsize("P") != 8:
        print("Python 3.11 x64 is required. Detected:", sys.version, file=sys.stderr)
        return 1
    if "--dependencies" in sys.argv:
        # Match main.py's native-library import order.
        import ctranslate2
        import tokenizers
        from PySide6 import QtCore, QtGui, QtWidgets
        import sqlite3
        with sqlite3.connect(":memory:") as db:
            db.execute("CREATE VIRTUAL TABLE probe USING fts5(text)")
        print("Dependencies OK: Qt", QtCore.__version__, "CTranslate2", ctranslate2.__version__)
    print("Python OK:", sys.executable)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
