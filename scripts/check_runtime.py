"""Console checks used by install.cmd; no model or user configuration is changed."""
import struct
import sys
import sysconfig


def supported_runtime(version, bits, implementation, free_threaded=False):
    return ((3, 10) <= tuple(version[:2]) < (3, 14)
            and bits == 64 and implementation == "cpython" and not free_threaded)


def main():
    if not supported_runtime(sys.version_info, struct.calcsize("P") * 8,
                             sys.implementation.name, sysconfig.get_config_var("Py_GIL_DISABLED")):
        print("CPython 3.10-3.13 x64 (standard build) is required. Detected:", sys.version, file=sys.stderr)
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
