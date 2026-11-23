#!/usr/bin/env python3
"""Windows AI Computer-Use Guard (v0.2.3):
- Pure Win32 UpdateLayeredWindow (Per-Pixel Alpha) + Pillow rendering:
  * Soft ice-blue semi-transparent glowing rounded thin border (Win11 radius)
  * Frosted dark-glass floating pill banner with glowing dot & ESC badge
  * Fully click-through & visible to both local monitor and remote viewers
- Dedicated pure Win32 GetMessageW hook thread (decoupled from UI):
  * Allows ONLY AI_MAGIC_TAG (0x41475943) events
  * Blocks ALL other physical & remote-desktop (e.g. GameViewer) inputs except Esc
- 100ms Win32 timer watchdog for abort.flag, stop.flag, dynamic target & timeout
"""
from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
import json
from pathlib import Path
import sys
import threading
import time

from PIL import Image, ImageDraw, ImageFilter, ImageFont

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
gdi32 = ctypes.windll.gdi32
kernel32 = ctypes.windll.kernel32

WH_KEYBOARD_LL = 13
WH_MOUSE_LL = 14
WM_KEYDOWN = 0x0100
WM_SYSKEYDOWN = 0x0104
WM_DESTROY = 0x0002
WM_QUIT = 0x0012
WM_TIMER = 0x0113
VK_ESCAPE = 0x1B

WS_POPUP = 0x80000000
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOPMOST = 0x00000008
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000

SW_SHOWNOACTIVATE = 4
ULW_ALPHA = 0x00000002
AC_SRC_OVER = 0x00
AC_SRC_ALPHA = 0x01
DIB_RGB_COLORS = 0
BI_RGB = 0

SM_CXSCREEN = 0
SM_CYSCREEN = 1

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


class SIZE(ctypes.Structure):
    _fields_ = [("cx", wintypes.LONG), ("cy", wintypes.LONG)]


class BLENDFUNCTION(ctypes.Structure):
    _fields_ = [
        ("BlendOp", wintypes.BYTE),
        ("BlendFlags", wintypes.BYTE),
        ("SourceConstantAlpha", wintypes.BYTE),
        ("AlphaFormat", wintypes.BYTE),
    ]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [
        ("bmiHeader", BITMAPINFOHEADER),
        ("bmiColors", wintypes.DWORD * 3),
    ]


HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)


class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.UINT),
        ("style", wintypes.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HICON),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
        ("hIconSm", wintypes.HICON),
    ]


# Explicit 64-bit safe Win32 signatures
kernel32.GetCurrentThreadId.argtypes = []
kernel32.GetCurrentThreadId.restype = wintypes.DWORD
kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
kernel32.GetModuleHandleW.restype = wintypes.HINSTANCE

user32.GetSystemMetrics.argtypes = [ctypes.c_int]
user32.GetSystemMetrics.restype = ctypes.c_int
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
user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.DefWindowProcW.restype = LRESULT
user32.RegisterClassExW.argtypes = [ctypes.POINTER(WNDCLASSEXW)]
user32.RegisterClassExW.restype = wintypes.ATOM
user32.CreateWindowExW.argtypes = [
    wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID,
]
user32.CreateWindowExW.restype = wintypes.HWND
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.ShowWindow.restype = wintypes.BOOL
user32.DestroyWindow.argtypes = [wintypes.HWND]
user32.DestroyWindow.restype = wintypes.BOOL
user32.SetTimer.argtypes = [wintypes.HWND, ctypes.c_size_t, wintypes.UINT, ctypes.c_void_p]
user32.SetTimer.restype = ctypes.c_size_t
user32.KillTimer.argtypes = [wintypes.HWND, ctypes.c_size_t]
user32.KillTimer.restype = wintypes.BOOL
user32.GetDC.argtypes = [wintypes.HWND]
user32.GetDC.restype = wintypes.HDC
user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
user32.ReleaseDC.restype = ctypes.c_int
user32.UpdateLayeredWindow.argtypes = [
    wintypes.HWND, wintypes.HDC, ctypes.POINTER(wintypes.POINT), ctypes.POINTER(SIZE),
    wintypes.HDC, ctypes.POINTER(wintypes.POINT), wintypes.COLORREF,
    ctypes.POINTER(BLENDFUNCTION), wintypes.DWORD,
]
user32.UpdateLayeredWindow.restype = wintypes.BOOL

gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
gdi32.CreateCompatibleDC.restype = wintypes.HDC
gdi32.DeleteDC.argtypes = [wintypes.HDC]
gdi32.DeleteDC.restype = wintypes.BOOL
gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
gdi32.SelectObject.restype = wintypes.HGDIOBJ
gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
gdi32.DeleteObject.restype = wintypes.BOOL
gdi32.CreateDIBSection.argtypes = [
    wintypes.HDC, ctypes.POINTER(BITMAPINFO), wintypes.UINT,
    ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, wintypes.DWORD,
]
gdi32.CreateDIBSection.restype = wintypes.HBITMAP


def _load_font(size: int, bold: bool = False):
    candidates = (
        ["C:/Windows/Fonts/msyhbd.ttc", "C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/segoeuib.ttf"]
        if bold
        else ["C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/segoeui.ttf"]
    )
    for fp in candidates:
        if Path(fp).is_file():
            try:
                return ImageFont.truetype(fp, size=size)
            except Exception:
                pass
    return ImageFont.load_default()


def _render_border_image(sw: int, sh: int) -> Image.Image:
    """Render soft ice-blue glowing rounded thin border at 1/2 scale then upscale."""
    rw = max(320, sw // 2)
    rh = max(200, sh // 2)
    inset = 4
    radius = 10

    glow = Image.new("RGBA", (rw, rh), (0, 0, 0, 0))
    dg = ImageDraw.Draw(glow)
    dg.rounded_rectangle(
        [inset, inset, rw - inset - 1, rh - inset - 1],
        radius=radius,
        outline=(56, 189, 248, 150),
        width=4,
    )
    glow = glow.filter(ImageFilter.GaussianBlur(radius=3.5))

    dc = ImageDraw.Draw(glow)
    dc.rounded_rectangle(
        [inset, inset, rw - inset - 1, rh - inset - 1],
        radius=radius,
        outline=(147, 215, 255, 225),
        width=2,
    )
    return glow.resize((sw, sh), Image.Resampling.BILINEAR)


def _render_pill_image(target: str, scale: float) -> Image.Image:
    """Render frosted-glass style rounded floating pill with ice-blue glow."""
    pad = int(round(14 * scale))
    pill_h = int(round(42 * scale))
    font_main = _load_font(int(round(14 * scale)), bold=True)
    font_badge = _load_font(int(round(12 * scale)), bold=True)

    t_short = (target or "").strip()
    if len(t_short) > 18:
        t_short = t_short[:17] + "…"
    main_text = (
        f"AI 正在操控 [{t_short}] · 请勿操作键鼠"
        if t_short
        else "AI 正在操控电脑 · 请勿操作键鼠"
    )
    badge_text = "ESC 退出"

    tmp = ImageDraw.Draw(Image.new("RGBA", (10, 10)))
    mb = tmp.textbbox((0, 0), main_text, font=font_main)
    bb = tmp.textbbox((0, 0), badge_text, font=font_badge)
    main_w = mb[2] - mb[0]
    main_h = mb[3] - mb[1]
    badge_tw = bb[2] - bb[0]
    badge_th = bb[3] - bb[1]

    dot_r = int(round(4.5 * scale))
    badge_pad_x = int(round(11 * scale))
    badge_w = badge_tw + badge_pad_x * 2
    badge_h = int(round(24 * scale))

    gap1 = int(round(18 * scale))
    gap2 = int(round(12 * scale))
    gap3 = int(round(16 * scale))
    pill_w = gap1 + dot_r * 2 + gap2 + main_w + gap3 + badge_w + int(round(14 * scale))

    total_w = pill_w + pad * 2
    total_h = pill_h + pad * 2
    radius = pill_h // 2

    # Outer ice-blue soft glow shadow
    canvas = Image.new("RGBA", (total_w, total_h), (0, 0, 0, 0))
    glow = Image.new("RGBA", (total_w, total_h), (0, 0, 0, 0))
    dg = ImageDraw.Draw(glow)
    dg.rounded_rectangle(
        [pad, pad, pad + pill_w, pad + pill_h],
        radius=radius,
        fill=(15, 23, 42, 95),
        outline=(56, 189, 248, 165),
        width=max(2, int(round(2.5 * scale))),
    )
    glow = glow.filter(ImageFilter.GaussianBlur(radius=max(3.0, 5.0 * scale)))
    canvas = Image.alpha_composite(canvas, glow)

    # Crisp dark translucent pill body + thin ice-blue rim
    d = ImageDraw.Draw(canvas)
    d.rounded_rectangle(
        [pad, pad, pad + pill_w, pad + pill_h],
        radius=radius,
        fill=(15, 23, 42, 222),
        outline=(147, 215, 255, 165),
        width=max(1, int(round(1.2 * scale))),
    )

    # Glowing ice-blue status dot
    dot_cx = pad + gap1 + dot_r
    dot_cy = pad + pill_h // 2
    d.ellipse(
        [dot_cx - dot_r - 2, dot_cy - dot_r - 2, dot_cx + dot_r + 2, dot_cy + dot_r + 2],
        fill=(56, 189, 248, 90),
    )
    d.ellipse(
        [dot_cx - dot_r, dot_cy - dot_r, dot_cx + dot_r, dot_cy + dot_r],
        fill=(125, 211, 252, 255),
    )

    # Main text
    tx = dot_cx + dot_r + gap2
    ty = pad + (pill_h - main_h) // 2 - mb[1]
    d.text((tx, ty), main_text, font=font_main, fill=(241, 245, 249, 250))

    # Right ESC badge
    bx = tx + main_w + gap3
    by = pad + (pill_h - badge_h) // 2
    d.rounded_rectangle(
        [bx, by, bx + badge_w, by + badge_h],
        radius=badge_h // 2,
        fill=(56, 189, 248, 48),
        outline=(125, 211, 252, 130),
        width=1,
    )
    btx = bx + (badge_w - badge_tw) // 2 - bb[0]
    bty = by + (badge_h - badge_th) // 2 - bb[1]
    d.text((btx, bty), badge_text, font=font_badge, fill=(186, 230, 253, 250))

    return canvas


def _apply_layered_image(hwnd: int, img: Image.Image, x: int, y: int) -> bool:
    w, h = img.size
    # Convert to premultiplied RGBA then swap R/B -> premultiplied BGRA for ULW_ALPHA
    premul = img.convert("RGBa")
    r, g, b, a = premul.split()
    bgra = Image.merge("RGBA", (b, g, r, a)).tobytes()

    hdc_screen = user32.GetDC(None)
    hdc_mem = gdi32.CreateCompatibleDC(hdc_screen)

    bmi = BITMAPINFO()
    bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bmi.bmiHeader.biWidth = w
    bmi.bmiHeader.biHeight = -h  # top-down DIB
    bmi.bmiHeader.biPlanes = 1
    bmi.bmiHeader.biBitCount = 32
    bmi.bmiHeader.biCompression = BI_RGB

    bits_ptr = ctypes.c_void_p()
    hbitmap = gdi32.CreateDIBSection(
        hdc_mem, ctypes.byref(bmi), DIB_RGB_COLORS, ctypes.byref(bits_ptr), None, 0
    )
    if not hbitmap:
        gdi32.DeleteDC(hdc_mem)
        user32.ReleaseDC(None, hdc_screen)
        return False

    ctypes.memmove(bits_ptr, bgra, len(bgra))
    old_bmp = gdi32.SelectObject(hdc_mem, hbitmap)

    pt_dst = wintypes.POINT(int(x), int(y))
    sz = SIZE(w, h)
    pt_src = wintypes.POINT(0, 0)
    blend = BLENDFUNCTION(AC_SRC_OVER, 0, 255, AC_SRC_ALPHA)

    ok = bool(
        user32.UpdateLayeredWindow(
            hwnd,
            hdc_screen,
            ctypes.byref(pt_dst),
            ctypes.byref(sz),
            hdc_mem,
            ctypes.byref(pt_src),
            0,
            ctypes.byref(blend),
            ULW_ALPHA,
        )
    )

    gdi32.SelectObject(hdc_mem, old_bmp)
    gdi32.DeleteObject(hbitmap)
    gdi32.DeleteDC(hdc_mem)
    user32.ReleaseDC(None, hdc_screen)
    return ok


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

    def stop_hooks() -> None:
        tid = hook_tid_box[0]
        if tid:
            try:
                user32.PostThreadMessageW(tid, WM_QUIT, 0, 0)
            except Exception:
                pass
        hook_thread.join(timeout=0.5)

    sw = max(640, user32.GetSystemMetrics(SM_CXSCREEN))
    sh = max(480, user32.GetSystemMetrics(SM_CYSCREEN))
    ui_scale = max(1.0, min(1.5, sw / 1920.0))

    hinst = kernel32.GetModuleHandleW(None)
    cls_name = "AGYComputerUseOverlayV23"

    state_box = {
        "target": target.strip(),
        "last_hb": time.time(),
        "border_hwnd": None,
        "pill_hwnd": None,
    }

    def _shutdown_windows() -> None:
        stop_event.set()
        stop_hooks()
        for key in ("pill_hwnd", "border_hwnd"):
            hw = state_box[key]
            if hw:
                state_box[key] = None
                try:
                    user32.KillTimer(hw, 1)
                except Exception:
                    pass
                try:
                    user32.DestroyWindow(hw)
                except Exception:
                    pass
        user32.PostQuitMessage(0)

    def _update_pill(new_target: str) -> None:
        pill_hwnd = state_box["pill_hwnd"]
        if not pill_hwnd:
            return
        pill_img = _render_pill_image(new_target, ui_scale)
        px = (sw - pill_img.width) // 2
        py = int(round(12 * ui_scale))
        _apply_layered_image(pill_hwnd, pill_img, px, py)

    def wnd_proc(hwnd, msg, wparam, lparam) -> int:
        if msg == WM_TIMER and wparam == 1:
            if stop_event.is_set() or abort_file.exists() or stop_file.exists():
                _shutdown_windows()
                return 0

            if heartbeat_file.exists():
                try:
                    val = float(heartbeat_file.read_text(encoding="utf-8").strip())
                    if val > state_box["last_hb"]:
                        state_box["last_hb"] = val
                except Exception:
                    pass

            if timeout > 0 and (time.time() - state_box["last_hb"]) > timeout:
                _shutdown_windows()
                return 0

            if state_file.exists():
                try:
                    st = json.loads(state_file.read_text(encoding="utf-8"))
                    new_t = str(st.get("target") or "").strip()
                    if new_t != state_box["target"]:
                        state_box["target"] = new_t
                        _update_pill(new_t)
                except Exception:
                    pass
            return 0
        if msg == WM_DESTROY:
            return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    wnd_cb = WNDPROC(wnd_proc)
    wc = WNDCLASSEXW()
    wc.cbSize = ctypes.sizeof(WNDCLASSEXW)
    wc.lpfnWndProc = wnd_cb
    wc.hInstance = hinst
    wc.lpszClassName = cls_name
    user32.RegisterClassExW(ctypes.byref(wc))

    ex_style = WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOPMOST | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE

    border_hwnd = user32.CreateWindowExW(
        ex_style, cls_name, "", WS_POPUP, 0, 0, sw, sh, None, None, hinst, None
    )
    pill_hwnd = user32.CreateWindowExW(
        ex_style, cls_name, "", WS_POPUP, 0, 0, 10, 10, None, None, hinst, None
    )
    state_box["border_hwnd"] = border_hwnd
    state_box["pill_hwnd"] = pill_hwnd

    border_img = _render_border_image(sw, sh)
    ok_b = _apply_layered_image(border_hwnd, border_img, 0, 0)
    pill_img = _render_pill_image(state_box["target"], ui_scale)
    ok_p = _apply_layered_image(
        pill_hwnd, pill_img, (sw - pill_img.width) // 2, int(round(12 * ui_scale))
    )

    user32.ShowWindow(border_hwnd, SW_SHOWNOACTIVATE)
    user32.ShowWindow(pill_hwnd, SW_SHOWNOACTIVATE)
    print(f"overlay_ready={ok_b and ok_p} border={ok_b} pill={ok_p}", file=sys.stderr, flush=True)

    user32.SetTimer(border_hwnd, 1, 100, None)

    msg = wintypes.MSG()
    try:
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
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
