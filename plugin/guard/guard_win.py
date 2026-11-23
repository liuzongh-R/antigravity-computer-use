#!/usr/bin/env python3
"""Windows AI Computer-Use Guard (v0.2.0):
- Dedicated pure Win32 GetMessageW hook thread (decoupled from Tkinter GUI)
- Allows ONLY AI_MAGIC_TAG (0x41475943) events; blocks ALL other physical &
  remote-desktop (e.g. GameViewer) mouse & keyboard inputs except Esc
- Codex-style high-contrast floating banner + 6px blue screen border
- Visible to both local monitor & remote capture (no WDA_EXCLUDEFROMCAPTURE)
- 100ms watchdog for abort.flag, stop.flag, dynamic target & heartbeat timeout
"""
from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
import json
import sys
import threading
import time
import tkinter as tk
from pathlib import Path

AI_MAGIC_TAG = 0x41475943  # 'AGYC'

# Enable DPI awareness before creating Tk windows
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
kernel32 = ctypes.windll.kernel32

WH_KEYBOARD_LL = 13
WH_MOUSE_LL = 14
WM_KEYDOWN = 0x0100
WM_SYSKEYDOWN = 0x0104
WM_QUIT = 0x0012
VK_ESCAPE = 0x1B

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

user32.GetParent.argtypes = [wintypes.HWND]
user32.GetParent.restype = wintypes.HWND

user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.GetWindowLongW.restype = wintypes.LONG

user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.LONG]
user32.SetWindowLongW.restype = wintypes.LONG

user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
user32.SetWindowsHookExW.restype = HHOOK

user32.CallNextHookEx.argtypes = [HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
user32.CallNextHookEx.restype = LRESULT

user32.UnhookWindowsHookEx.argtypes = [HHOOK]
user32.UnhookWindowsHookEx.restype = wintypes.BOOL

user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
user32.GetMessageW.restype = wintypes.BOOL

user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
user32.TranslateMessage.restype = wintypes.BOOL

user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
user32.DispatchMessageW.restype = LRESULT

user32.PostQuitMessage.argtypes = [ctypes.c_int]
user32.PostQuitMessage.restype = None

user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.PostThreadMessageW.restype = wintypes.BOOL

kernel32.GetCurrentThreadId.argtypes = []
kernel32.GetCurrentThreadId.restype = wintypes.DWORD


def _style_overlay_window(win: tk.Misc) -> None:
    win.update_idletasks()
    hwnd = user32.GetParent(win.winfo_id()) or win.winfo_id()
    ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    user32.SetWindowLongW(
        hwnd,
        GWL_EXSTYLE,
        ex_style | WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOPMOST | WS_EX_TOOLWINDOW,
    )


def _format_title(target: str) -> str:
    if target:
        return f"● AI 正在操控 [{target}] — 请勿移动鼠标或操作键盘"
    return "● AI 正在操控电脑 — 请勿移动鼠标或操作键盘"


def _create_border_edges(root: tk.Tk, sw: int, sh: int, thickness: int = 6) -> list[tk.Toplevel]:
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
        edge.attributes("-alpha", 0.88)
        edge.configure(bg="#3B82F6")
        edge.geometry(geom)
        _style_overlay_window(edge)
        edges.append(edge)
    return edges


def run_guard(state_dir: Path, target: str, timeout: float) -> None:
    abort_file = state_dir / "abort.flag"
    stop_file = state_dir / "stop.flag"
    heartbeat_file = state_dir / "heartbeat.txt"
    state_file = state_dir / "guard_state.json"

    stop_event = threading.Event()
    hooks_ready = threading.Event()
    hook_tid_box = [0]

    def hook_thread_main() -> None:
        hook_tid_box[0] = int(kernel32.GetCurrentThreadId())

        def kb_proc(nCode: int, wParam: int, lParam: int) -> int:
            if nCode >= 0:
                kb = ctypes.cast(lParam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                if kb.dwExtraInfo == AI_MAGIC_TAG:
                    return user32.CallNextHookEx(None, nCode, wParam, lParam)
                if wParam in (WM_KEYDOWN, WM_SYSKEYDOWN) and kb.vkCode == VK_ESCAPE:
                    try:
                        abort_file.write_text("esc", encoding="utf-8")
                    except Exception:
                        pass
                    stop_event.set()
                    user32.PostQuitMessage(0)
                    return 1
                return 1
            return user32.CallNextHookEx(None, nCode, wParam, lParam)

        def mouse_proc(nCode: int, wParam: int, lParam: int) -> int:
            if nCode >= 0:
                ms = ctypes.cast(lParam, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
                if ms.dwExtraInfo == AI_MAGIC_TAG:
                    return user32.CallNextHookEx(None, nCode, wParam, lParam)
                return 1
            return user32.CallNextHookEx(None, nCode, wParam, lParam)

        kb_cb = HOOKPROC(kb_proc)
        ms_cb = HOOKPROC(mouse_proc)
        kb_hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, kb_cb, None, 0)
        ms_hook = user32.SetWindowsHookExW(WH_MOUSE_LL, ms_cb, None, 0)
        print(f"hooks_installed kb={bool(kb_hook)} ms={bool(ms_hook)}", file=sys.stderr, flush=True)
        hooks_ready.set()

        msg = wintypes.MSG()
        try:
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
        finally:
            if kb_hook:
                user32.UnhookWindowsHookEx(kb_hook)
            if ms_hook:
                user32.UnhookWindowsHookEx(ms_hook)

    hook_thread = threading.Thread(target=hook_thread_main, daemon=True)
    hook_thread.start()
    hooks_ready.wait(timeout=2.0)

    root = tk.Tk()
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    root.attributes("-alpha", 0.95)
    root.configure(bg="#3B82F6")

    card = tk.Frame(root, bg="#0F172A", padx=26, pady=12)
    card.pack(padx=2, pady=2)

    current_target = target
    lbl_title = tk.Label(
        card,
        text=_format_title(current_target),
        fg="#F9FAFB",
        bg="#0F172A",
        font=("Microsoft YaHei UI", 13, "bold"),
    )
    lbl_title.pack()

    lbl_sub = tk.Label(
        card,
        text="除 Esc 外所有键鼠操作均已禁止 · 按 Esc 立即退出 AI 操作",
        fg="#FCD34D",
        bg="#0F172A",
        font=("Microsoft YaHei UI", 11),
        pady=3,
    )
    lbl_sub.pack()

    def _position_banner() -> None:
        root.update_idletasks()
        sw_ = root.winfo_screenwidth()
        ww = root.winfo_reqwidth()
        wh = root.winfo_reqheight()
        root.geometry(f"{ww}x{wh}+{(sw_ - ww) // 2}+20")

    _position_banner()
    _style_overlay_window(root)

    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()
    edges = _create_border_edges(root, sw, sh, thickness=6)

    def stop_hooks() -> None:
        tid = hook_tid_box[0]
        if tid:
            try:
                user32.PostThreadMessageW(tid, WM_QUIT, 0, 0)
            except Exception:
                pass
        hook_thread.join(timeout=0.5)

    def shutdown_all() -> None:
        stop_event.set()
        stop_hooks()
        for edge in edges:
            try:
                edge.destroy()
            except Exception:
                pass
        try:
            root.destroy()
        except Exception:
            pass

    last_hb = time.time()

    def watchdog_tick() -> None:
        nonlocal last_hb, current_target
        if stop_event.is_set() or abort_file.exists() or stop_file.exists():
            shutdown_all()
            return

        if heartbeat_file.exists():
            try:
                val = float(heartbeat_file.read_text(encoding="utf-8").strip())
                if val > last_hb:
                    last_hb = val
            except Exception:
                pass

        if timeout > 0 and (time.time() - last_hb) > timeout:
            shutdown_all()
            return

        if state_file.exists():
            try:
                st = json.loads(state_file.read_text(encoding="utf-8"))
                new_target = str(st.get("target") or "")
                if new_target != current_target:
                    current_target = new_target
                    lbl_title.config(text=_format_title(current_target))
                    _position_banner()
            except Exception:
                pass

        root.after(100, watchdog_tick)

    root.after(100, watchdog_tick)
    try:
        root.mainloop()
    finally:
        stop_hooks()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-dir", required=True)
    parser.add_argument("--target", default="")
    parser.add_argument("--timeout", type=float, default=45.0)
    args = parser.parse_args()
    run_guard(Path(args.state_dir), args.target, args.timeout)


if __name__ == "__main__":
    main()
