#!/usr/bin/env python3
"""macOS AI Computer-Use Guard:
- Shows floating banner & 4px highlight border ONLY inside the target window
  when the target app is frontmost (hides when user switches away).
- Uses primary screen height (screens()[0]) for CGWindowBounds -> Cocoa conversion.
- Listens via CGEventTap:
  * Allows AI-injected events (kCGEventSourceUnixProcessID > 0).
  * When target app is NOT frontmost: allows user physical input (including
    clicking the target window to focus it).
  * When target app IS frontmost: pressing Esc aborts AI operation; other
    physical keyboard/mouse events are blocked.
- Heartbeat watchdog: auto-exits if no heartbeat within --timeout seconds.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time


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
    heartbeat_file = state_dir / "heartbeat.txt"
    state_file = state_dir / "guard_state.json"

    current_target = target.strip()

    def is_target_frontmost() -> bool:
        app = AppKit.NSWorkspace.sharedWorkspace().frontmostApplication()
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
        for w in windows:
            owner = (w.get("kCGWindowOwnerName") or "").lower()
            title = (w.get("kCGWindowName") or "").lower()
            layer = w.get("kCGWindowLayer", 0)
            if layer != 0:
                continue
            if not t_lower or t_lower in owner or t_lower in title:
                b = w.get("kCGWindowBounds")
                if b and b.get("Width", 0) > 100 and b.get("Height", 0) > 60:
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

    banner_w, banner_h = 380.0, 36.0
    panel = _make_panel(
        banner_w,
        banner_h,
        AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(0.07, 0.09, 0.15, 0.92),
    )

    def _banner_text(t: str) -> str:
        return f"🤖 AI 正在操作 [{t or '当前页面'}] · 点击此页按 Esc 退出"

    label = AppKit.NSTextField.labelWithString_(_banner_text(current_target))
    label.setTextColor_(AppKit.NSColor.whiteColor())
    label.setFont_(AppKit.NSFont.boldSystemFontOfSize_(12))
    label.setFrame_(AppKit.NSMakeRect(12, 8, banner_w - 24, 20))
    panel.contentView().addSubview_(label)

    border_color = AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(0.23, 0.51, 0.96, 0.70)
    border_panels = [_make_panel(10, 4, border_color) for _ in range(4)]

    def hide_all() -> None:
        panel.orderOut_(None)
        for bp in border_panels:
            bp.orderOut_(None)

    last_hb = time.time()

    def update_banner(_timer) -> None:
        nonlocal last_hb, current_target
        if abort_file.exists():
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
                    label.setStringValue_(_banner_text(current_target))
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
        t = 4.0

        # Banner centered at top inside target window
        px = bx + max(0.0, (bw - banner_w) / 2.0)
        py = sh - by - banner_h - 8.0
        panel.setFrameOrigin_(AppKit.NSMakePoint(px, py))
        panel.orderFront_(None)

        # 4 border edges (top, bottom, left, right) in Cocoa bottom-left coords
        edge_rects = [
            AppKit.NSMakeRect(bx, sh - by - t, bw, t),
            AppKit.NSMakeRect(bx, sh - (by + bh), bw, t),
            AppKit.NSMakeRect(bx, sh - (by + bh), t, bh),
            AppKit.NSMakeRect(bx + bw - t, sh - (by + bh), t, bh),
        ]
        for bp, rect in zip(border_panels, edge_rects):
            bp.setFrame_display_(rect, True)
            bp.orderFront_(None)

    AppKit.NSTimer.scheduledTimerWithTimeInterval_repeats_block_(0.2, True, update_banner)

    def event_callback(proxy, event_type, event, refcon):
        # Allow AI-injected events (pid > 0)
        src_pid = Quartz.CGEventGetIntegerValueField(event, Quartz.kCGEventSourceUnixProcessID)
        if src_pid > 0:
            return event

        # If user is not focused on the target app, allow input so user can work or click to focus
        if not is_target_frontmost():
            return event

        # Target app is frontmost: Esc aborts; all other physical inputs are blocked
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
        | Quartz.CGEventMaskBit(Quartz.kCGEventLeftMouseDown)
        | Quartz.CGEventMaskBit(Quartz.kCGEventLeftMouseUp)
        | Quartz.CGEventMaskBit(Quartz.kCGEventRightMouseDown)
        | Quartz.CGEventMaskBit(Quartz.kCGEventRightMouseUp)
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
    else:
        print(
            "Warning: CGEventTapCreate returned None (check Accessibility permission)",
            file=sys.stderr,
        )

    AppHelper.runEventLoop()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-dir", required=True)
    parser.add_argument("--target", default="")
    parser.add_argument("--timeout", type=float, default=20.0)
    args = parser.parse_args()
    run_guard(Path(args.state_dir), args.target, args.timeout)


if __name__ == "__main__":
    main()
