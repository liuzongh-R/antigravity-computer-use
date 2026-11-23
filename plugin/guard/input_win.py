#!/usr/bin/env python3
"""Windows native input & window control with AI_MAGIC_TAG signature (v0.2.0)."""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import re
import time

AI_MAGIC_TAG = 0x41475943  # 'AGYC'

# Enable per-monitor DPI awareness
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

user32 = ctypes.windll.user32

INPUT_MOUSE = 0
INPUT_KEYBOARD = 1

MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_VIRTUALDESK = 0x4000
MOUSEEVENTF_ABSOLUTE = 0x8000

KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004

SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79

SW_RESTORE = 9


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class _INPUTunion(ctypes.Union):
    _fields_ = [
        ("mi", MOUSEINPUT),
        ("ki", KEYBDINPUT),
        ("hi", HARDWAREINPUT),
    ]


class INPUT(ctypes.Structure):
    _fields_ = [
        ("type", wintypes.DWORD),
        ("union", _INPUTunion),
    ]


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", wintypes.LONG),
        ("top", wintypes.LONG),
        ("right", wintypes.LONG),
        ("bottom", wintypes.LONG),
    ]


user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
user32.SendInput.restype = wintypes.UINT
user32.GetSystemMetrics.argtypes = [ctypes.c_int]
user32.GetSystemMetrics.restype = ctypes.c_int
user32.GetForegroundWindow.argtypes = []
user32.GetForegroundWindow.restype = wintypes.HWND
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsWindowVisible.restype = wintypes.BOOL
user32.IsIconic.argtypes = [wintypes.HWND]
user32.IsIconic.restype = wintypes.BOOL
user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
user32.GetWindowTextLengthW.restype = ctypes.c_int
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowTextW.restype = ctypes.c_int
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(RECT)]
user32.GetWindowRect.restype = wintypes.BOOL
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.ShowWindow.restype = wintypes.BOOL
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.SetForegroundWindow.restype = wintypes.BOOL
user32.BringWindowToTop.argtypes = [wintypes.HWND]
user32.BringWindowToTop.restype = wintypes.BOOL

WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user32.EnumWindows.argtypes = [WNDENUMPROC, wintypes.LPARAM]
user32.EnumWindows.restype = wintypes.BOOL

VK_MAP: dict[str, int] = {
    "backspace": 0x08, "back": 0x08,
    "tab": 0x09,
    "clear": 0x0C,
    "enter": 0x0D, "return": 0x0D,
    "shift": 0x10, "lshift": 0xA0, "rshift": 0xA1,
    "ctrl": 0x11, "control": 0x11, "lctrl": 0xA2, "rctrl": 0xA3,
    "alt": 0x12, "menu": 0x12, "option": 0x12, "lalt": 0xA4, "ralt": 0xA5,
    "pause": 0x13, "capslock": 0x14, "caps": 0x14,
    "esc": 0x1B, "escape": 0x1B,
    "space": 0x20, " ": 0x20,
    "pageup": 0x21, "pgup": 0x21, "prior": 0x21,
    "pagedown": 0x22, "pgdn": 0x22, "next": 0x22,
    "end": 0x23, "home": 0x24,
    "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
    "select": 0x29, "print": 0x2A, "printscreen": 0x2C, "prtsc": 0x2C,
    "insert": 0x2D, "ins": 0x2D, "delete": 0x2E, "del": 0x2E,
    "win": 0x5B, "lwin": 0x5B, "super": 0x5B, "cmd": 0x5B, "command": 0x5B, "rwin": 0x5C,
    "apps": 0x5D,
    "num0": 0x60, "num1": 0x61, "num2": 0x62, "num3": 0x63, "num4": 0x64,
    "num5": 0x65, "num6": 0x66, "num7": 0x67, "num8": 0x68, "num9": 0x69,
    "multiply": 0x6A, "add": 0x6B, "subtract": 0x6D, "decimal": 0x6E, "divide": 0x6F,
    "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73, "f5": 0x74, "f6": 0x75,
    "f7": 0x76, "f8": 0x77, "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B,
    "numlock": 0x90, "scrolllock": 0x91,
    ";": 0xBA, "semicolon": 0xBA,
    "=": 0xBB, "equal": 0xBB, "plus": 0xBB,
    ",": 0xBC, "comma": 0xBC,
    "-": 0xBD, "minus": 0xBD,
    ".": 0xBE, "period": 0xBE,
    "/": 0xBF, "slash": 0xBF,
    "`": 0xC0, "grave": 0xC0, "tilde": 0xC0,
    "[": 0xDB, "lbracket": 0xDB,
    "\\": 0xDC, "backslash": 0xDC,
    "]": 0xDD, "rbracket": 0xDD,
    "'": 0xDE, "quote": 0xDE,
}
for _c in "abcdefghijklmnopqrstuvwxyz":
    VK_MAP[_c] = ord(_c.upper())
for _d in "0123456789":
    VK_MAP[_d] = ord(_d)

EXTENDED_VKS = {
    0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28,
    0x2C, 0x2D, 0x2E, 0x5B, 0x5C, 0x5D, 0x6F, 0xA3, 0xA5,
}
MODIFIER_NAMES = {
    "ctrl", "control", "lctrl", "rctrl",
    "alt", "option", "lalt", "ralt",
    "shift", "lshift", "rshift",
    "win", "lwin", "rwin", "super", "cmd", "command",
}


def _send_inputs(items: list[INPUT]) -> None:
    if not items:
        return
    arr = (INPUT * len(items))(*items)
    user32.SendInput(len(items), arr, ctypes.sizeof(INPUT))


def to_virtual_absolute(phys_x: int, phys_y: int) -> tuple[int, int]:
    vx = user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
    vy = user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
    vw = max(1, user32.GetSystemMetrics(SM_CXVIRTUALSCREEN))
    vh = max(1, user32.GetSystemMetrics(SM_CYVIRTUALSCREEN))
    ax = int(round((phys_x - vx) * 65535.0 / max(1, vw - 1)))
    ay = int(round((phys_y - vy) * 65535.0 / max(1, vh - 1)))
    ax = max(0, min(65535, ax))
    ay = max(0, min(65535, ay))
    return ax, ay


def _mouse_input(dx: int, dy: int, flags: int, mouse_data: int = 0) -> INPUT:
    return INPUT(
        type=INPUT_MOUSE,
        union=_INPUTunion(
            mi=MOUSEINPUT(
                dx=dx,
                dy=dy,
                mouseData=ctypes.c_uint32(mouse_data).value,
                dwFlags=flags,
                time=0,
                dwExtraInfo=AI_MAGIC_TAG,
            )
        ),
    )


def _key_input(vk: int = 0, scan: int = 0, flags: int = 0) -> INPUT:
    return INPUT(
        type=INPUT_KEYBOARD,
        union=_INPUTunion(
            ki=KEYBDINPUT(
                wVk=vk,
                wScan=scan,
                dwFlags=flags,
                time=0,
                dwExtraInfo=AI_MAGIC_TAG,
            )
        ),
    )


def move_mouse(x: int, y: int) -> None:
    ax, ay = to_virtual_absolute(int(x), int(y))
    _send_inputs([_mouse_input(ax, ay, MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK)])


def _button_flags(button: str) -> tuple[int, int]:
    b = (button or "left").lower()
    if b == "right":
        return MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP
    if b == "middle":
        return MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP
    return MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP


def click(x: int, y: int, button: str = "left", clicks: int = 1) -> None:
    ax, ay = to_virtual_absolute(int(x), int(y))
    move_flags = MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK
    down_f, up_f = _button_flags(button)
    _send_inputs([_mouse_input(ax, ay, move_flags)])
    time.sleep(0.015)
    for idx in range(max(1, int(clicks))):
        _send_inputs([
            _mouse_input(ax, ay, move_flags | down_f),
            _mouse_input(ax, ay, move_flags | up_f),
        ])
        if idx + 1 < clicks:
            time.sleep(0.04)


def drag(
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    duration: float = 0.25,
    button: str = "left",
) -> None:
    down_f, up_f = _button_flags(button)
    move_flags = MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK
    ax1, ay1 = to_virtual_absolute(int(x1), int(y1))
    _send_inputs([_mouse_input(ax1, ay1, move_flags)])
    time.sleep(0.02)
    _send_inputs([_mouse_input(ax1, ay1, move_flags | down_f)])

    steps = max(4, min(30, int(max(0.05, float(duration)) / 0.015)))
    dt = max(0.05, float(duration)) / steps
    for i in range(1, steps + 1):
        t = i / steps
        cx = int(round(x1 + (x2 - x1) * t))
        cy = int(round(y1 + (y2 - y1) * t))
        acx, acy = to_virtual_absolute(cx, cy)
        _send_inputs([_mouse_input(acx, acy, move_flags)])
        time.sleep(dt)

    ax2, ay2 = to_virtual_absolute(int(x2), int(y2))
    _send_inputs([_mouse_input(ax2, ay2, move_flags | up_f)])


def scroll(clicks: int, x: int | None = None, y: int | None = None) -> None:
    if x is not None and y is not None:
        move_mouse(int(x), int(y))
        time.sleep(0.015)
    delta = int(clicks) * 120
    _send_inputs([_mouse_input(0, 0, MOUSEEVENTF_WHEEL, mouse_data=delta)])


def type_text(text: str) -> None:
    if not text:
        return
    raw = text.encode("utf-16-le")
    items: list[INPUT] = []
    for i in range(0, len(raw), 2):
        code_unit = int.from_bytes(raw[i : i + 2], "little")
        items.append(_key_input(vk=0, scan=code_unit, flags=KEYEVENTF_UNICODE))
        items.append(_key_input(vk=0, scan=code_unit, flags=KEYEVENTF_UNICODE | KEYEVENTF_KEYUP))
    # Send in chunks to avoid dropping large payloads
    for start in range(0, len(items), 64):
        _send_inputs(items[start : start + 64])
        if start + 64 < len(items):
            time.sleep(0.005)


def _resolve_vk(key_name: str) -> int:
    k = key_name.strip().lower()
    if k in VK_MAP:
        return VK_MAP[k]
    raise ValueError(f"Unsupported key name: {key_name!r}")


def _press_combo(combo: list[str]) -> None:
    vks = [_resolve_vk(k) for k in combo]
    downs: list[INPUT] = []
    ups: list[INPUT] = []
    for vk in vks:
        ext = KEYEVENTF_EXTENDEDKEY if vk in EXTENDED_VKS else 0
        downs.append(_key_input(vk=vk, flags=ext))
    for vk in reversed(vks):
        ext = KEYEVENTF_EXTENDEDKEY if vk in EXTENDED_VKS else 0
        ups.append(_key_input(vk=vk, flags=ext | KEYEVENTF_KEYUP))
    _send_inputs(downs)
    time.sleep(0.02)
    _send_inputs(ups)


def press_keys(keys) -> None:
    if isinstance(keys, str):
        s = keys.strip()
        if "+" in s and len(s) > 1:
            _press_combo([part for part in s.split("+") if part])
        else:
            _press_combo([s])
        return

    if isinstance(keys, list):
        if not keys:
            return
        if all(isinstance(x, str) for x in keys) and keys[0].strip().lower() in MODIFIER_NAMES:
            _press_combo(keys)
            return
        for item in keys:
            if isinstance(item, list):
                _press_combo([str(x) for x in item])
            else:
                press_keys(str(item))
            time.sleep(0.02)
        return

    raise ValueError(f"Unsupported keys format: {keys!r}")


def list_windows() -> list[dict]:
    fg = user32.GetForegroundWindow()
    results: list[dict] = []

    def _cb(hwnd, lparam) -> bool:
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value.strip()
        if not title:
            return True
        rect = RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return True
        w = rect.right - rect.left
        h = rect.bottom - rect.top
        if w <= 0 or h <= 0:
            return True
        results.append(
            {
                "title": title,
                "left": int(rect.left),
                "top": int(rect.top),
                "width": int(w),
                "height": int(h),
                "is_active": hwnd == fg,
                "is_minimized": bool(user32.IsIconic(hwnd)),
                "hwnd": int(hwnd),
            }
        )
        return True

    cb = WNDENUMPROC(_cb)
    user32.EnumWindows(cb, 0)
    return results


def activate_window(title_pattern: str, use_regex: bool = False) -> str:
    if not title_pattern:
        raise ValueError("title_pattern cannot be empty")
    wins = list_windows()
    matched = None
    if use_regex:
        rx = re.compile(title_pattern, re.IGNORECASE)
        for w in wins:
            if rx.search(w["title"]):
                matched = w
                break
    else:
        pat = title_pattern.lower()
        for w in wins:
            if w["title"].lower() == pat:
                matched = w
                break
        if matched is None:
            for w in wins:
                if pat in w["title"].lower():
                    matched = w
                    break

    if matched is None:
        raise RuntimeError(f"No window found matching pattern: {title_pattern!r}")

    hwnd = matched["hwnd"]
    if matched["is_minimized"]:
        user32.ShowWindow(hwnd, SW_RESTORE)
        time.sleep(0.08)

    # Brief tagged Alt tap to bypass Windows foreground lock cleanly
    _send_inputs([
        _key_input(vk=0x12, flags=0),
        _key_input(vk=0x12, flags=KEYEVENTF_KEYUP),
    ])
    user32.SetForegroundWindow(hwnd)
    user32.BringWindowToTop(hwnd)
    return matched["title"]
