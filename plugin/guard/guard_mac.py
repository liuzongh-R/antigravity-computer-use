#!/usr/bin/env python3
"""macOS AI Computer-Use Guard (v0.2.1):
- True single-window lock ONLY:
  * Never blocks mouse movement (kCGEventMouseMoved is NOT tapped).
  * Does nothing when target is empty (never locks global OS or Antigravity).
  * Shows banner & 6px blue border ONLY inside the target window when frontmost.
  * Allows clicks outside target window bounds (Dock, menu bar, other apps)
    and allows Command+Tab so the user can freely switch away anytime.
  * When target window IS frontmost, clicks/scrolls inside it and non-Esc keys
    are blocked; pressing Esc aborts AI operation immediately.
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

    state = {
        "target": target.strip(),
        "target_pid": None,
        "bounds": None,
        "frontmost": False,
    }

    def _frontmost_app():
        return AppKit.NSWorkspace.sharedWorkspace().frontmostApplication()

    def _matches_target(owner: str, title: str, bundle: str, t_lower: str) -> bool:
        if not t_lower:
            return False
        return (t_lower in owner) or (t_lower in title) or (t_lower in bundle)

    def refresh_target_window() -> tuple[bool, dict | None]:
        t_lower = state["target"].lower()
        if not t_lower:
            state["target_pid"] = None
            state["bounds"] = None
            state["frontmost"] = False
            return False, None

        front_app = _frontmost_app()
        if not front_app:
            state["frontmost"] = False
            state["bounds"] = None
            return False, None

        front_pid = int(front_app.processIdentifier())
        front_name = (front_app.localizedName() or "").lower()
        front_bundle = (front_app.bundleIdentifier() or "").lower()

        options = Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements
        windows = Quartz.CGWindowListCopyWindowInfo(options, Quartz.kCGNullWindowID)

        matched_front_bounds = None
        for w in windows:
            if w.get("kCGWindowLayer", 0) != 0:
                continue
            b = w.get("kCGWindowBounds")
            if not b or b.get("Width", 0) <= 100 or b.get("Height", 0) <= 60:
                continue
            wpid = int(w.get("kCGWindowOwnerPID") or 0)
            if wpid != front_pid:
                continue
            owner = (w.get("kCGWindowOwnerName") or "").lower()
            title = (w.get("kCGWindowName") or "").lower()
            if (
                _matches_target(owner, title, front_bundle, t_lower)
                or (t_lower in front_name)
            ):
                matched_front_bounds = {
                    "X": float(b["X"]),
                    "Y": float(b["Y"]),
                    "Width": float(b["Width"]),
                    "Height": float(b["Height"]),
                }
                state["target_pid"] = front_pid
                break

        is_front = matched_front_bounds is not None
        state["frontmost"] = is_front
        state["bounds"] = matched_front_bounds
        return is_front, matched_front_bounds

    def is_target_frontmost_fast() -> bool:
        if not state["target"]:
            return False
        front_app = _frontmost_app()
        if not front_app:
            return False
        if state["target_pid"] is not None:
            return int(front_app.processIdentifier()) == state["target_pid"]
        t_lower = state["target"].lower()
        name = (front_app.localizedName() or "").lower()
        bundle = (front_app.bundleIdentifier() or "").lower()
        return t_lower in name or t_lower in bundle

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
        return f"● AI 正在操控 [{t}] — 请勿移动鼠标或操作键盘"

    lbl_title = AppKit.NSTextField.labelWithString_(_title_text(state["target"] or "目标窗口"))
    lbl_title.setTextColor_(AppKit.NSColor.whiteColor())
    lbl_title.setFont_(AppKit.NSFont.boldSystemFontOfSize_(13))
    lbl_title.setAlignment_(AppKit.NSTextAlignmentCenter)
    lbl_title.setFrame_(AppKit.NSMakeRect(10, 28, banner_w - 24, 20))
    inner.addSubview_(lbl_title)

    lbl_sub = AppKit.NSTextField.labelWithString_(
        "仅锁定当前窗口内操作 · 点击外部可随时切换，点回此页按 Esc 退出"
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
        nonlocal last_hb
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
                if new_t != state["target"]:
                    state["target"] = new_t
                    state["target_pid"] = None
                    if new_t:
                        lbl_title.setStringValue_(_title_text(new_t))
            except Exception:
                pass

        is_front, bounds = refresh_target_window()
        if not is_front or not bounds:
            hide_all()
            return

        bx = bounds["X"]
        by = bounds["Y"]
        bw = bounds["Width"]
        bh = bounds["Height"]
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

    AppKit.NSTimer.scheduledTimerWithTimeInterval_repeats_block_(0.12, True, update_banner)

    def _point_inside_target(pt) -> bool:
        b = state["bounds"]
        if not b:
            return False
        return (
            b["X"] <= pt.x <= b["X"] + b["Width"]
            and b["Y"] <= pt.y <= b["Y"] + b["Height"]
        )

    def event_callback(proxy, event_type, event, refcon):
        # 1. Always allow AI-signed events
        tag = Quartz.CGEventGetIntegerValueField(event, Quartz.kCGEventSourceUserData)
        if tag == AI_MAGIC_TAG:
            return event

        # 2. If target is unset or not frontmost, never block anything
        if not is_target_frontmost_fast():
            return event

        # 3. Keyboard events while target window is frontmost
        if event_type in (Quartz.kCGEventKeyDown, Quartz.kCGEventKeyUp):
            keycode = Quartz.CGEventGetIntegerValueField(event, Quartz.kCGKeyboardEventKeycode)
            flags = Quartz.CGEventGetFlags(event)
            # Allow Command+Tab so user can always switch apps via keyboard
            if keycode == 48 and (flags & Quartz.kCGEventFlagMaskCommand):
                return event
            if event_type == Quartz.kCGEventKeyDown and keycode == 53:  # Esc
                try:
                    abort_file.write_text("esc", encoding="utf-8")
                except Exception:
                    pass
                hide_all()
                AppHelper.stopEventLoop()
                return None
            return None

        # 4. Mouse click/drag/scroll events: ONLY block inside the target window bounds
        pt = Quartz.CGEventGetLocation(event)
        if not _point_inside_target(pt):
            return event

        return None

    # Note: kCGEventMouseMoved is intentionally excluded so cursor movement is never locked
    mask = (
        Quartz.CGEventMaskBit(Quartz.kCGEventKeyDown)
        | Quartz.CGEventMaskBit(Quartz.kCGEventKeyUp)
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
