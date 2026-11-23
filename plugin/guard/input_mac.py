#!/usr/bin/env python3
"""macOS native input & window control with AI_MAGIC_TAG signature (v0.2.0)."""
from __future__ import annotations

import re
import time

import AppKit
import Quartz

AI_MAGIC_TAG = 0x41475943  # 'AGYC'

# Virtual keycodes for US QWERTY & common keys on macOS
MAC_KEYCODES: dict[str, int] = {
    "a": 0x00, "s": 0x01, "d": 0x02, "f": 0x03, "h": 0x04, "g": 0x05, "z": 0x06, "x": 0x07,
    "c": 0x08, "v": 0x09, "b": 0x0B, "q": 0x0C, "w": 0x0D, "e": 0x0E, "r": 0x0F,
    "y": 0x10, "t": 0x11, "1": 0x12, "2": 0x13, "3": 0x14, "4": 0x15, "6": 0x16, "5": 0x17,
    "=": 0x18, "equal": 0x18, "plus": 0x18, "9": 0x19, "7": 0x1A, "-": 0x1B, "minus": 0x1B,
    "8": 0x1C, "0": 0x1D, "]": 0x1E, "rbracket": 0x1E, "o": 0x1F,
    "u": 0x20, "[": 0x21, "lbracket": 0x21, "i": 0x22, "p": 0x23,
    "enter": 0x24, "return": 0x24, "l": 0x25, "j": 0x26, "'": 0x27, "quote": 0x27,
    "k": 0x28, ";": 0x29, "semicolon": 0x29, "\\": 0x2A, "backslash": 0x2A,
    ",": 0x2B, "comma": 0x2B, "/": 0x2C, "slash": 0x2C, "n": 0x2D, "m": 0x2E,
    ".": 0x2F, "period": 0x2F, "tab": 0x30, "space": 0x31, " ": 0x31,
    "`": 0x32, "grave": 0x32, "tilde": 0x32,
    "backspace": 0x33, "back": 0x33, "esc": 0x35, "escape": 0x35,
    "command": 0x37, "cmd": 0x37, "win": 0x37, "super": 0x37,
    "shift": 0x38, "lshift": 0x38, "capslock": 0x39, "caps": 0x39,
    "alt": 0x3A, "option": 0x3A, "lalt": 0x3A,
    "ctrl": 0x3B, "control": 0x3B, "lctrl": 0x3B,
    "rshift": 0x3C, "ralt": 0x3D, "rctrl": 0x3E,
    "f17": 0x40, "f18": 0x4F, "f19": 0x50, "f20": 0x5A,
    "f5": 0x60, "f6": 0x61, "f7": 0x62, "f3": 0x63, "f8": 0x64, "f9": 0x65,
    "f11": 0x67, "f13": 0x69, "f16": 0x6A, "f14": 0x6B, "f10": 0x6D,
    "f12": 0x6F, "f15": 0x71, "insert": 0x72, "ins": 0x72,
    "home": 0x73, "pageup": 0x74, "pgup": 0x74, "delete": 0x75, "del": 0x75,
    "f4": 0x76, "end": 0x77, "f2": 0x78, "pagedown": 0x79, "pgdn": 0x79,
    "f1": 0x7A, "left": 0x7B, "right": 0x7C, "down": 0x7D, "up": 0x7E,
}

MODIFIER_NAMES = {
    "command", "cmd", "win", "super",
    "ctrl", "control", "lctrl", "rctrl",
    "alt", "option", "lalt", "ralt",
    "shift", "lshift", "rshift",
}

MODIFIER_FLAGS = {
    "command": Quartz.kCGEventFlagMaskCommand,
    "cmd": Quartz.kCGEventFlagMaskCommand,
    "win": Quartz.kCGEventFlagMaskCommand,
    "super": Quartz.kCGEventFlagMaskCommand,
    "ctrl": Quartz.kCGEventFlagMaskControl,
    "control": Quartz.kCGEventFlagMaskControl,
    "lctrl": Quartz.kCGEventFlagMaskControl,
    "rctrl": Quartz.kCGEventFlagMaskControl,
    "alt": Quartz.kCGEventFlagMaskAlternate,
    "option": Quartz.kCGEventFlagMaskAlternate,
    "lalt": Quartz.kCGEventFlagMaskAlternate,
    "ralt": Quartz.kCGEventFlagMaskAlternate,
    "shift": Quartz.kCGEventFlagMaskShift,
    "lshift": Quartz.kCGEventFlagMaskShift,
    "rshift": Quartz.kCGEventFlagMaskShift,
}


def _tag_and_post(ev) -> None:
    Quartz.CGEventSetIntegerValueField(ev, Quartz.kCGEventSourceUserData, AI_MAGIC_TAG)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, ev)


def _mouse_types(button: str):
    b = (button or "left").lower()
    if b == "right":
        return (
            Quartz.kCGEventRightMouseDown,
            Quartz.kCGEventRightMouseUp,
            Quartz.kCGEventRightMouseDragged,
            Quartz.kCGMouseButtonRight,
        )
    if b == "middle":
        return (
            Quartz.kCGEventOtherMouseDown,
            Quartz.kCGEventOtherMouseUp,
            Quartz.kCGEventOtherMouseDragged,
            Quartz.kCGMouseButtonCenter,
        )
    return (
        Quartz.kCGEventLeftMouseDown,
        Quartz.kCGEventLeftMouseUp,
        Quartz.kCGEventLeftMouseDragged,
        Quartz.kCGMouseButtonLeft,
    )


def move_mouse(x: int, y: int) -> None:
    pt = (float(x), float(y))
    ev = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventMouseMoved, pt, Quartz.kCGMouseButtonLeft)
    _tag_and_post(ev)


def click(x: int, y: int, button: str = "left", clicks: int = 1) -> None:
    pt = (float(x), float(y))
    down_t, up_t, _, btn = _mouse_types(button)
    move_ev = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventMouseMoved, pt, btn)
    _tag_and_post(move_ev)
    time.sleep(0.015)

    for idx in range(1, max(1, int(clicks)) + 1):
        ev_down = Quartz.CGEventCreateMouseEvent(None, down_t, pt, btn)
        Quartz.CGEventSetIntegerValueField(ev_down, Quartz.kCGMouseEventClickState, idx)
        _tag_and_post(ev_down)
        ev_up = Quartz.CGEventCreateMouseEvent(None, up_t, pt, btn)
        Quartz.CGEventSetIntegerValueField(ev_up, Quartz.kCGMouseEventClickState, idx)
        _tag_and_post(ev_up)
        if idx < clicks:
            time.sleep(0.04)


def drag(
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    duration: float = 0.25,
    button: str = "left",
) -> None:
    down_t, up_t, drag_t, btn = _mouse_types(button)
    _tag_and_post(Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventMouseMoved, (float(x1), float(y1)), btn))
    time.sleep(0.02)
    _tag_and_post(Quartz.CGEventCreateMouseEvent(None, down_t, (float(x1), float(y1)), btn))

    steps = max(4, min(30, int(max(0.05, float(duration)) / 0.015)))
    dt = max(0.05, float(duration)) / steps
    for i in range(1, steps + 1):
        t = i / steps
        cx = float(x1) + (float(x2) - float(x1)) * t
        cy = float(y1) + (float(y2) - float(y1)) * t
        _tag_and_post(Quartz.CGEventCreateMouseEvent(None, drag_t, (cx, cy), btn))
        time.sleep(dt)

    _tag_and_post(Quartz.CGEventCreateMouseEvent(None, up_t, (float(x2), float(y2)), btn))


def scroll(clicks: int, x: int | None = None, y: int | None = None) -> None:
    if x is not None and y is not None:
        move_mouse(int(x), int(y))
        time.sleep(0.015)
    ev = Quartz.CGEventCreateScrollWheelEvent(None, Quartz.kCGScrollEventUnitLine, 1, int(clicks))
    _tag_and_post(ev)


def type_text(text: str) -> None:
    if not text:
        return
    for start in range(0, len(text), 20):
        chunk = text[start : start + 20]
        ev_down = Quartz.CGEventCreateKeyboardEvent(None, 0, True)
        Quartz.CGEventKeyboardSetUnicodeString(ev_down, len(chunk), chunk)
        _tag_and_post(ev_down)
        ev_up = Quartz.CGEventCreateKeyboardEvent(None, 0, False)
        Quartz.CGEventKeyboardSetUnicodeString(ev_up, len(chunk), chunk)
        _tag_and_post(ev_up)
        if start + 20 < len(text):
            time.sleep(0.01)


def _press_combo(combo: list[str]) -> None:
    mods: list[str] = []
    keys: list[str] = []
    flags = 0
    for item in combo:
        k = item.strip().lower()
        if k in MODIFIER_FLAGS:
            mods.append(k)
            flags |= MODIFIER_FLAGS[k]
        else:
            keys.append(k)

    for m in mods:
        kc = MAC_KEYCODES[m]
        ev = Quartz.CGEventCreateKeyboardEvent(None, kc, True)
        Quartz.CGEventSetFlags(ev, flags)
        _tag_and_post(ev)

    for k in keys:
        if k not in MAC_KEYCODES:
            raise ValueError(f"Unsupported key name on macOS: {k!r}")
        kc = MAC_KEYCODES[k]
        ev_d = Quartz.CGEventCreateKeyboardEvent(None, kc, True)
        if flags:
            Quartz.CGEventSetFlags(ev_d, flags)
        _tag_and_post(ev_d)
        ev_u = Quartz.CGEventCreateKeyboardEvent(None, kc, False)
        if flags:
            Quartz.CGEventSetFlags(ev_u, flags)
        _tag_and_post(ev_u)

    time.sleep(0.02)
    for m in reversed(mods):
        kc = MAC_KEYCODES[m]
        ev = Quartz.CGEventCreateKeyboardEvent(None, kc, False)
        _tag_and_post(ev)


def press_keys(keys) -> None:
    if isinstance(keys, str):
        s = keys.strip()
        if "+" in s and len(s) > 1:
            _press_combo([p for p in s.split("+") if p])
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
    options = Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements
    windows = Quartz.CGWindowListCopyWindowInfo(options, Quartz.kCGNullWindowID)
    front_app = AppKit.NSWorkspace.sharedWorkspace().frontmostApplication()
    front_pid = front_app.processIdentifier() if front_app else None

    results: list[dict] = []
    for w in windows:
        if w.get("kCGWindowLayer", 0) != 0:
            continue
        b = w.get("kCGWindowBounds")
        if not b:
            continue
        bw = int(b.get("Width", 0))
        bh = int(b.get("Height", 0))
        if bw <= 60 or bh <= 40:
            continue
        owner = str(w.get("kCGWindowOwnerName") or "").strip()
        name = str(w.get("kCGWindowName") or "").strip()
        title = f"{owner} - {name}" if (owner and name and owner.lower() not in name.lower()) else (name or owner)
        if not title:
            continue
        pid = int(w.get("kCGWindowOwnerPID") or 0)
        results.append(
            {
                "title": title,
                "owner": owner,
                "left": int(b.get("X", 0)),
                "top": int(b.get("Y", 0)),
                "width": bw,
                "height": bh,
                "is_active": pid == front_pid,
                "pid": pid,
            }
        )
    return results


def activate_window(title_pattern: str, use_regex: bool = False) -> str:
    if not title_pattern:
        raise ValueError("title_pattern cannot be empty")
    wins = list_windows()
    matched = None
    if use_regex:
        rx = re.compile(title_pattern, re.IGNORECASE)
        for w in wins:
            if rx.search(w["title"]) or rx.search(w.get("owner", "")):
                matched = w
                break
    else:
        pat = title_pattern.lower()
        for w in wins:
            if w["title"].lower() == pat or w.get("owner", "").lower() == pat:
                matched = w
                break
        if matched is None:
            for w in wins:
                if pat in w["title"].lower() or pat in w.get("owner", "").lower():
                    matched = w
                    break

    if matched is None:
        raise RuntimeError(f"No window found matching pattern: {title_pattern!r}")

    app = AppKit.NSRunningApplication.runningApplicationWithProcessIdentifier_(matched["pid"])
    if app:
        app.activateWithOptions_(AppKit.NSApplicationActivateIgnoringOtherApps)
    return matched["title"]
