#!/usr/bin/env python3
"""macOS AI Computer-Use Guard (v0.2.0):
- Shows Codex-style floating banner & 6px blue border ONLY inside the target window
  when the target app is frontmost (hides when user switches away).
- Visible to both local screen & remote desktop viewers (no NSWindowSharingNone).
- Uses primary screen height (screens()[0]) for CGWindowBounds -> Cocoa conversion.
- Listens via CGEventTap:
  * Allows ONLY events signed with AI_MAGIC_TAG (kCGEventSourceUserData == 0x41475943).
  * When target app is NOT frontmost: allows user physical input (including
    clicking the target window to focus it).
  * When target app IS frontmost: pressing Esc aborts AI operation; all other
    physical keyboard/mouse events are blocked.
- 0.15s watchdog checks abort.flag, stop.flag, dynamic target & heartbeat timeout.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time

AI_MAGIC_TAG = 0x41475943  # 'AGYC'


def run_guard(state_dir: Path, target: str, timeout: float) -> None:
    try:
        import AppKit
        import Quartz
        from PyObjCTools import AppHelper
    except ImportError:
        print(
            "macOS guard requires pyobjc-framework-Cocoa and pyobjc-framework-Quartz",
            file=sys.stderr,
        )
        sys.exit(1)

    abort_file = state_dir / "abort.flag"
    stop_file = state_dir / "stop.flag"
    heartbeat_file = state_dir / "heartbeat.txt"
    state_file = state_dir / "guard_state.json"

    current_target = target.strip()

    def _frontmost_app():
        return AppKit.NSWorkspace.sharedWorkspace().frontmostApplication()

    def is_target_frontmost() -> bool:
        app = _frontmost_app()
        if not app:
            return False
        t_lower = current_target.lower()
        if not t_lower:
            return True
        name = (app.localizedName() or "").lower()
        bundle = (app.bundleIdentifier() or "").lower()
        return t_lower in name or t_lower in bundle

    def get_target_window_bounds():
        options = Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements
        windows = Quartz.CGWindowListCopyWindowInfo(options, Quartz.kCGNullWindowID)
        t_lower = current_target.lower()
        front_app = _frontmost_app()
        front_pid = front_app.processIdentifier() if front_app else None

        for w in windows:
            if w.get("kCGWindowLayer", 0) != 0:
                continue
            b = w.get("kCGWindowBounds")
            if not b or b.get("Width", 0) <= 100 or b.get("Height", 0) <= 60:
                continue
            if not t_lower:
                if front_pid is not None and w.get("kCGWindowOwnerPID") == front_pid:
                    return b
                continue
            owner = (w.get("kCGWindowOwnerName") or "").lower()
            title = (w.get("kCGWindowName") or "").lower()
            if t_lower in owner or t_lower in title:
                return b
        return None

    def primary_screen_height() -> float:
        screens = AppKit.NSScreen.screens()
        if screens and len(screens) > 0:
            return float(screens[0].frame().size.height)
        main = AppKit.NSScreen.mainScreen()
        return float(main.frame().size.height) if main else 900.0

    def _make_panel(w: float, h: float, color) -> object:
        p = AppKit.NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            AppKit.NSMakeRect(0, 0, w, h),
            AppKit.NSWindowStyleMaskBorderless | AppKit.NSWindowStyleMaskNonactivatingPanel,
            AppKit.NSBackingStoreBuffered,
            False,
        )
        p.setLevel_(AppKit.NSFloatingWindowLevel)
        p.setOpaque_(False)
        p.setBackgroundColor_(color)
        p.setIgnoresMouseEvents_(True)
        return p

    app = AppKit.NSApplication.sharedApplication()
    app.setActivationPolicy_(AppKit.NSApplicationActivationPolicyAccessory)

    banner_w, banner_h = 500.0, 58.0
    panel = _make_panel(
        banner_w,
        banner_h,
        AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(0.23, 0.51, 0.96, 0.96),
    )

    inner = AppKit.NSView.alloc().initWithFrame_(AppKit.NSMakeRect(2, 2, banner_w - 4, banner_h - 4))
    inner.setWantsLayer_(True)
    inner.layer().setBackgroundColor_(
        AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(0.06, 0.09, 0.16, 0.95).CGColor()
    )
    panel.contentView().addSubview_(inner)

    def _title_text(t: str) -> str:
        if t:
            return f"● AI 正在操控 [{t}] — 请勿移动鼠标或操作键盘"
        return "● AI 正在操控此窗口 — 请勿移动鼠标或操作键盘"

    lbl_title = AppKit.NSTextField.labelWithString_(_title_text(current_target))
    lbl_title.setTextColor_(AppKit.NSColor.whiteColor())
    lbl_title.setFont_(AppKit.NSFont.boldSystemFontOfSize_(13))
    lbl_title.setAlignment_(AppKit.NSTextAlignmentCenter)
    lbl_title.setFrame_(AppKit.NSMakeRect(10, 28, banner_w - 24, 20))
    inner.addSubview_(lbl_title)

    lbl_sub = AppKit.NSTextField.labelWithString_(
        "当前窗口输入已禁止 · 点击此页按 Esc 立即退出 AI 操作"
    )
    lbl_sub.setTextColor_(
        AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(0.99, 0.83, 0.30, 1.0)
    )
    lbl_sub.setFont_(AppKit.NSFont.systemFontOfSize_(11))
    lbl_sub.setAlignment_(AppKit.NSTextAlignmentCenter)
    lbl_sub.setFrame_(AppKit.NSMakeRect(10, 6, banner_w - 24, 18))
    inner.addSubview_(lbl_sub)

    border_color = AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(0.23, 0.51, 0.96, 0.88)
    border_panels = [_make_panel(10, 6, border_color) for _ in range(4)]

    def hide_all() -> None:
        panel.orderOut_(None)
        for bp in border_panels:
            bp.orderOut_(None)

    last_hb = time.time()

    def update_banner(_timer) -> None:
        nonlocal last_hb, current_target
        if abort_file.exists() or stop_file.exists():
            hide_all()
            AppHelper.stopEventLoop()
            return

        if heartbeat_file.exists():
            try:
                val = float(heartbeat_file.read_text(encoding="utf-8").strip())
                if val > last_hb:
                    last_hb = val
            except Exception:
                pass

        if timeout > 0 and (time.time() - last_hb) > timeout:
            hide_all()
            AppHelper.stopEventLoop()
            return

        if state_file.exists():
            try:
                st = json.loads(state_file.read_text(encoding="utf-8"))
                new_t = str(st.get("target") or "").strip()
                if new_t != current_target:
                    current_target = new_t
                    lbl_title.setStringValue_(_title_text(current_target))
            except Exception:
                pass

        if not is_target_frontmost():
            hide_all()
            return

        bounds = get_target_window_bounds()
        if not bounds:
            hide_all()
            return

        bx = float(bounds["X"])
        by = float(bounds["Y"])
        bw = float(bounds["Width"])
        bh = float(bounds["Height"])
        sh = primary_screen_height()
        t = 6.0

        px = bx + max(0.0, (bw - banner_w) / 2.0)
        py = sh - by - banner_h - 10.0
        panel.setFrameOrigin_(AppKit.NSMakePoint(px, py))
        panel.orderFront_(None)

        edge_rects = [
            AppKit.NSMakeRect(bx, sh - by - t, bw, t),
            AppKit.NSMakeRect(bx, sh - (by + bh), bw, t),
            AppKit.NSMakeRect(bx, sh - (by + bh), t, bh),
            AppKit.NSMakeRect(bx + bw - t, sh - (by + bh), t, bh),
        ]
        for bp, rect in zip(border_panels, edge_rects):
            bp.setFrame_display_(rect, True)
            bp.orderFront_(None)

    AppKit.NSTimer.scheduledTimerWithTimeInterval_repeats_block_(0.15, True, update_banner)

    def event_callback(proxy, event_type, event, refcon):
        # Allow ONLY AI-signed events
        tag = Quartz.CGEventGetIntegerValueField(event, Quartz.kCGEventSourceUserData)
        if tag == AI_MAGIC_TAG:
            return event

        # If user is not focused on the target app, allow input so user can work or click to focus
        if not is_target_frontmost():
            return event

        # Target app is frontmost: Esc aborts; all other inputs are blocked
        if event_type == Quartz.kCGEventKeyDown:
            keycode = Quartz.CGEventGetIntegerValueField(event, Quartz.kCGKeyboardEventKeycode)
            if keycode == 53:  # Esc
                try:
                    abort_file.write_text("esc", encoding="utf-8")
                except Exception:
                    pass
                hide_all()
                AppHelper.stopEventLoop()
                return None

        return None

    mask = (
        Quartz.CGEventMaskBit(Quartz.kCGEventKeyDown)
        | Quartz.CGEventMaskBit(Quartz.kCGEventKeyUp)
        | Quartz.CGEventMaskBit(Quartz.kCGEventMouseMoved)
        | Quartz.CGEventMaskBit(Quartz.kCGEventLeftMouseDown)
        | Quartz.CGEventMaskBit(Quartz.kCGEventLeftMouseUp)
        | Quartz.CGEventMaskBit(Quartz.kCGEventLeftMouseDragged)
        | Quartz.CGEventMaskBit(Quartz.kCGEventRightMouseDown)
        | Quartz.CGEventMaskBit(Quartz.kCGEventRightMouseUp)
        | Quartz.CGEventMaskBit(Quartz.kCGEventRightMouseDragged)
        | Quartz.CGEventMaskBit(Quartz.kCGEventOtherMouseDown)
        | Quartz.CGEventMaskBit(Quartz.kCGEventOtherMouseUp)
        | Quartz.CGEventMaskBit(Quartz.kCGEventOtherMouseDragged)
        | Quartz.CGEventMaskBit(Quartz.kCGEventScrollWheel)
    )
    tap = Quartz.CGEventTapCreate(
        Quartz.kCGSessionEventTap,
        Quartz.kCGHeadInsertEventTap,
        Quartz.kCGEventTapOptionDefault,
        mask,
        event_callback,
        None,
    )
    if tap:
        source = Quartz.CFMachPortCreateRunLoopSource(None, tap, 0)
        Quartz.CFRunLoopAddSource(
            Quartz.CFRunLoopGetCurrent(), source, Quartz.kCFRunLoopCommonModes
        )
        Quartz.CGEventTapEnable(tap, True)
        print("mac_event_tap_installed=True", file=sys.stderr, flush=True)
    else:
        print(
            "Warning: CGEventTapCreate returned None (check Accessibility permission)",
            file=sys.stderr,
            flush=True,
        )

    AppHelper.runEventLoop()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-dir", required=True)
    parser.add_argument("--target", default="")
    parser.add_argument("--timeout", type=float, default=45.0)
    args = parser.parse_args()
    run_guard(Path(args.state_dir), args.target, args.timeout)


if __name__ == "__main__":
    main()
