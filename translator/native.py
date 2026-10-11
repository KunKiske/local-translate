"""Small, typed Win32 bridge: hotkeys, foreground focus, and keyboard input."""
import ctypes
from ctypes import wintypes

from PySide6.QtCore import QAbstractNativeEventFilter

user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.GetForegroundWindow.restype = wintypes.HWND
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.SetForegroundWindow.restype = wintypes.BOOL
user32.IsWindow.argtypes = [wintypes.HWND]
user32.IsWindow.restype = wintypes.BOOL
user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
user32.RegisterHotKey.restype = wintypes.BOOL
user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
user32.GetClipboardSequenceNumber.restype = wintypes.DWORD
user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
user32.GetAsyncKeyState.restype = ctypes.c_short


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.c_size_t)]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG),
                ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class INPUTUNION(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("value",)
    _fields_ = [("type", wintypes.DWORD), ("value", INPUTUNION)]


user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
user32.SendInput.restype = wintypes.UINT


def foreground():
    return user32.GetForegroundWindow()


def focus(hwnd):
    if not hwnd or not user32.IsWindow(hwnd):
        return False
    user32.SetForegroundWindow(hwnd)
    return foreground() == hwnd


def modifiers_pressed():
    return any(user32.GetAsyncKeyState(vk) & 0x8000 for vk in (0x10, 0x11, 0x12, 0x5B, 0x5C))


def shortcut(letter):
    if modifiers_pressed():
        raise RuntimeError("请松开 Ctrl / Shift / Alt / Win 键后重试。")
    events = (INPUT * 4)()
    for event, vk, flags in zip(events, (0x11, ord(letter), ord(letter), 0x11), (0, 0, 2, 2)):
        event.type = 1
        event.ki = KEYBDINPUT(vk, 0, flags, 0, 0)
    if user32.SendInput(4, events, ctypes.sizeof(INPUT)) != 4:
        raise RuntimeError("Windows 未接受模拟按键，请手动按 Ctrl+V，或检查目标程序的管理员权限。")


def parse_hotkey(text):
    parts = text.upper().replace(" ", "").split("+")
    mods = 0x4000
    for modifier in parts[:-1]:
        if modifier not in {"CTRL", "ALT", "SHIFT", "WIN"}:
            raise ValueError("快捷键示例：F1、Ctrl+Alt+T")
        mods |= {"CTRL": 2, "ALT": 1, "SHIFT": 4, "WIN": 8}[modifier]
    key = parts[-1]
    if key.startswith("F") and key[1:].isdigit() and 1 <= int(key[1:]) <= 11:
        vk = 0x70 + int(key[1:]) - 1
    elif len(key) == 1 and key.isascii() and key.isalnum():
        vk = ord(key)
        if mods == 0x4000:
            raise ValueError("字母或数字快捷键需要搭配 Ctrl / Alt / Shift。")
    elif key in {"SPACE", "TAB", "ENTER", "BACKSPACE", "DELETE", "INSERT", "HOME", "END", "PAGEUP", "PAGEDOWN", "LEFT", "UP", "RIGHT", "DOWN"} and mods != 0x4000:
        vk = {"SPACE": 0x20, "TAB": 9, "ENTER": 13, "BACKSPACE": 8, "DELETE": 0x2E,
              "INSERT": 0x2D, "HOME": 0x24, "END": 0x23, "PAGEUP": 0x21,
              "PAGEDOWN": 0x22, "LEFT": 0x25, "UP": 0x26, "RIGHT": 0x27, "DOWN": 0x28}[key]
    else:
        raise ValueError("请使用 F1–F11 或 Ctrl+Alt+T 这样的组合。")
    return mods, vk


class Hotkeys(QAbstractNativeEventFilter):
    def __init__(self, callback):
        super().__init__()
        self.callback = callback
        self.keys = None

    def configure(self, hotkey, naming_hotkey="F2", dictionary_hotkey="F3"):
        names = (hotkey, naming_hotkey, dictionary_hotkey)
        parsed = [parse_hotkey(name) for name in names]
        if len(set(parsed)) != len(parsed):
            raise ValueError("翻译、代码命名与字典不能使用相同的快捷键。")
        previous = self.keys
        self.unregister()
        for ident, (mods, vk) in enumerate(parsed, 1):
            if not user32.RegisterHotKey(None, ident, mods, vk):
                self.unregister()
                if previous:
                    for old_id, (old_mods, old_vk) in enumerate(previous, 1):
                        user32.RegisterHotKey(None, old_id, old_mods, old_vk)
                    self.keys = previous
                raise ValueError(f"快捷键 {names[ident - 1]} 已被其他程序占用，请修改。")
        self.keys = parsed

    def unregister(self):
        for ident in (1, 2, 3):
            user32.UnregisterHotKey(None, ident)
        self.keys = None

    def nativeEventFilter(self, event_type, message):
        msg = wintypes.MSG.from_address(int(message))
        if msg.message == 0x0312 and msg.wParam in (1, 2, 3):
            self.callback(int(msg.wParam))
            return True, 0
        return False, 0
