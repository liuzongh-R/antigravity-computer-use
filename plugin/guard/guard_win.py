#!/usr/bin/env python3
"""Windows AI Computer-Use Guard:
- DPI aware topmost click-through banner: 'AI 正在操作桌面 · 按 Esc 退出'
- 4px semi-transparent blue highlight border around screen edges
- 64-bit safe low-level keyboard & mouse hooks:
  * Allows injected (AI) events (LLKHF_INJECTED / LLMHF_INJECTED)
  * Blocks physical mouse & keyboard input
  * Allows physical Esc -> writes abort.flag and exits cleanly
- Heartbeat watchdog: auto-exits and unlocks if no heartbeat within --timeout seconds
"""
from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
import json
import threading
import time
import tkinter as tk
from pathlib import Path

# Enable DPI awareness before creating Tk windows
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

WH_KEYBOARD_LL = 13
WH_MOUSE_LL = 14
WM_KEYDOWN = 0x0100
WM_SYSKEYDOWN = 0x0104
VK_ESCAPE = 0x1B
LLKHF_INJECTED = 0x10
LLMHF_INJECTED = 0x01

GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOPMOST = 0x00000008
WS_EX_TOOLWINDOW = 0x00000080

LRESULT = ctypes.c_ssize_t
HHOOK = wintypes.HANDLE


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("pt", wintypes.POINT),
        ("mouseData", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)

user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
user32.SetWindowsHookExW.restype = HHOOK

user32.CallNextHookEx.argtypes = [HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
user32.CallNextHookEx.restype = LRESULT

user32.UnhookWindowsHookEx.argtypes = [HHOOK]
user32.UnhookWindowsHookEx.restype = wintypes.BOOL


def _make_click_through(win: tk.Misc) -> None:
    win.update_idletasks()
    hwnd = user32.GetParent(win.winfo_id()) or win.winfo_id()
    ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    user32.SetWindowLongW(
        hwnd,
        GWL_EXSTYLE,
        ex_style | WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOPMOST | WS_EX_TOOLWINDOW,
    )


def _format_label(target: str) -> str:
    if target:
        return f"🤖 AI 正在操作 [{target}] · 按 Esc 退出"
    return "🤖 AI 正在操作桌面 · 按 Esc 退出"


def _create_border_edges(root: tk.Tk, sw: int, sh: int, thickness: int = 4) -> list[tk.Toplevel]:
    specs = [
        f"{sw}x{thickness}+0+0",
        f"{sw}x{thickness}+0+{sh - thickness}",
        f"{thickness}x{sh}+0+0",
        f"{thickness}x{sh}+{sw - thickness}+0",
    ]
    edges: list[tk.Toplevel] = []
    for geom in specs:
        edge = tk.Toplevel(root)
        edge.overrideredirect(True)
        edge.attributes("-topmost", True)
        edge.attributes("-alpha", 0.65)
        edge.configure(bg="#3B82F6")
        edge.geometry(geom)
        _make_click_through(edge)
        edges.append(edge)
    return edges


def run_guard(state_dir: Path, target: str, timeout: float) -> None:
    abort_file = state_dir / "abort.flag"
    heartbeat_file = state_dir / "heartbeat.txt"
    state_file = state_dir / "guard_state.json"
    stop_event = threading.Event()

    root = tk.Tk()
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    root.attributes("-alpha", 0.92)
    root.configure(bg="#111827")

    current_target = target
    lbl = tk.Label(
        root,
        text=_format_label(current_target),
        fg="#F9FAFB",
        bg="#111827",
        font=("Microsoft YaHei UI", 11, "bold"),
        padx=18,
        pady=8,
    )
    lbl.pack()

    def _position_banner() -> None:
        root.update_idletasks()
        sw_ = root.winfo_screenwidth()
        ww = root.winfo_reqwidth()
        wh = root.winfo_reqheight()
        root.geometry(f"{ww}x{wh}+{(sw_ - ww) // 2}+16")

    _position_banner()
    _make_click_through(root)

    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()
    edges = _create_border_edges(root, sw, sh, thickness=4)

    def shutdown_ui() -> None:
        for edge in edges:
            try:
                edge.destroy()
            except Exception:
                pass
        try:
            root.destroy()
        except Exception:
            pass

    def trigger_abort() -> None:
        try:
            abort_file.write_text("esc", encoding="utf-8")
        except Exception:
            pass
        stop_event.set()
        root.after(0, shutdown_ui)

    def kb_proc(nCode: int, wParam: int, lParam: int) -> int:
        if nCode >= 0:
            kb = ctypes.cast(lParam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
            is_injected = bool(kb.flags & LLKHF_INJECTED)
            if not is_injected:
                if wParam in (WM_KEYDOWN, WM_SYSKEYDOWN) and kb.vkCode == VK_ESCAPE:
                    trigger_abort()
                    return 1
                return 1
        return user32.CallNextHookEx(None, nCode, wParam, lParam)

    def mouse_proc(nCode: int, wParam: int, lParam: int) -> int:
        if nCode >= 0:
            ms = ctypes.cast(lParam, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
            is_injected = bool(ms.flags & LLMHF_INJECTED)
            if not is_injected:
                return 1
        return user32.CallNextHookEx(None, nCode, wParam, lParam)

    kb_cb = HOOKPROC(kb_proc)
    ms_cb = HOOKPROC(mouse_proc)

    h_mod = kernel32.GetModuleHandleW(None)
    kb_hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, kb_cb, h_mod, 0)
    ms_hook = user32.SetWindowsHookExW(WH_MOUSE_LL, ms_cb, h_mod, 0)

    last_hb = time.time()

    def watchdog_tick() -> None:
        nonlocal last_hb, current_target
        if stop_event.is_set() or abort_file.exists():
            shutdown_ui()
            return

        if heartbeat_file.exists():
            try:
                val = float(heartbeat_file.read_text(encoding="utf-8").strip())
                if val > last_hb:
                    last_hb = val
            except Exception:
                pass

        if timeout > 0 and (time.time() - last_hb) > timeout:
            stop_event.set()
            shutdown_ui()
            return

        if state_file.exists():
            try:
                st = json.loads(state_file.read_text(encoding="utf-8"))
                new_target = str(st.get("target") or "")
                if new_target != current_target:
                    current_target = new_target
                    lbl.config(text=_format_label(current_target))
                    _position_banner()
            except Exception:
                pass

        root.after(500, watchdog_tick)

    root.after(500, watchdog_tick)
    try:
        root.mainloop()
    finally:
        if kb_hook:
            user32.UnhookWindowsHookEx(kb_hook)
        if ms_hook:
            user32.UnhookWindowsHookEx(ms_hook)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-dir", required=True)
    parser.add_argument("--target", default="")
    parser.add_argument("--timeout", type=float, default=20.0)
    args = parser.parse_args()
    run_guard(Path(args.state_dir), args.target, args.timeout)


if __name__ == "__main__":
    main()
