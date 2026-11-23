#!/usr/bin/env python3
"""macOS AI Computer-Use Guard (v0.2.2):
- Strictly pins to a single window identity (target_pid, target_wid).
- Never locks global OS, Antigravity, other apps, or even other windows of the
  same application!
- Never blocks mouse movement (kCGEventMouseMoved is NOT tapped).
- Allows clicks outside the bound window bounds, Command+Tab, and Command+~.
- When the bound window is top-frontmost: displays Codex banner + 6px blue
  border inside it and blocks clicks/scrolls inside + non-Esc keys.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time

AI_MAGIC_TAG = 0x41475943  # 'AGYC'


def run_guard(
    state_dir: Path,
    target: str,
    target_pid: int,
    target_wid: int,
    timeout: float,
) -> None:
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
        "target_pid": target_pid if target_pid > 0 else None,
        "target_wid": target_wid if target_wid > 0 else None,
        "bounds": None,
        "is_locked_now": False,
        "logged_key": None,
    }

    def _frontmost_app():
        return AppKit.NSWorkspace.sharedWorkspace().frontmostApplication()

    def _resolve_target_once(windows) -> None:
        t_lower = state["target"].lower()
        if not t_lower:
            return
        include_agy = "antigravity" in t_lower
        for w in windows:
            if w.get("kCGWindowLayer", 0) != 0:
                continue
            b = w.get("kCGWindowBounds")
            if not b or b.get("Width", 0) <= 100 or b.get("Height", 0) <= 60:
                continue
            owner = str(w.get("kCGWindowOwnerName") or "").strip()
            name = str(w.get("kCGWindowName") or "").strip()
            if not include_agy and "antigravity" in owner.lower():
                continue
            combined = f"{owner} - {name}".lower()
            if t_lower in owner.lower() or t_lower in name.lower() or t_lower in combined:
                state["target_pid"] = int(w.get("kCGWindowOwnerPID") or 0) or None
                state["target_wid"] = int(w.get("kCGWindowNumber") or 0) or None
                break

    def _log_binding_if_changed() -> None:
        key = (state["target_pid"], state["target_wid"], state["target"])
        if key != state["logged_key"] and (state["target_pid"] or state["target"]):
            state["logged_key"] = key
            print(
                f"mac_guard_bound pid={state['target_pid']} wid={state['target_wid']} target={state['target']!r}",
                file=sys.stderr,
                flush=True,
            )

    def refresh_target_window() -> tuple[bool, dict | None]:
        if state["target_pid"] is None and state["target_wid"] is None and not state["target"]:
            state["is_locked_now"] = False
            state["bounds"] = None
            return False, None

        options = Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements
        windows = Quartz.CGWindowListCopyWindowInfo(options, Quartz.kCGNullWindowID)

        if state["target_pid"] is None and state["target_wid"] is None:
            _resolve_target_once(windows)

        _log_binding_if_changed()

        t_pid = state["target_pid"]
        t_wid = state["target_wid"]
        if t_pid is None and t_wid is None:
            state["is_locked_now"] = False
            state["bounds"] = None
            return False, None

        front_app = _frontmost_app()
        if not front_app:
            state["is_locked_now"] = False
            state["bounds"] = None
            return False, None

        front_pid = int(front_app.processIdentifier())
        if t_pid is not None and front_pid != t_pid:
            state["is_locked_now"] = False
            state["bounds"] = None
            return False, None

        # Find the top-most (first in Z-order) valid window owned by front_pid
        top_w = None
        for w in windows:
            if w.get("kCGWindowLayer", 0) != 0:
                continue
            b = w.get("kCGWindowBounds")
            if not b or b.get("Width", 0) <= 100 or b.get("Height", 0) <= 60:
                continue
            wpid = int(w.get("kCGWindowOwnerPID") or 0)
            if wpid == front_pid:
                top_w = w
                break

        if top_w is None:
            state["is_locked_now"] = False
            state["bounds"] = None
            return False, None

        top_wid = int(top_w.get("kCGWindowNumber") or 0)
        if t_wid is not None and top_wid != t_wid:
            # User switched to a different window within the same application
            state["is_locked_now"] = False
            state["bounds"] = None
            return False, None

        if state["target_wid"] is None and top_wid > 0:
            state["target_wid"] = top_wid
            _log_binding_if_changed()

        b = top_w["kCGWindowBounds"]
        bounds = {
            "X": float(b["X"]),
            "Y": float(b["Y"]),
            "Width": float(b["Width"]),
            "Height": float(b["Height"]),
        }
        state["bounds"] = bounds
        state["is_locked_now"] = True
        return True, bounds

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
        return f"● AI 正在操控 [{t or '目标窗口'}] — 请勿移动鼠标或操作键盘"

    lbl_title = AppKit.NSTextField.labelWithString_(_title_text(state["target"]))
    lbl_title.setTextColor_(AppKit.NSColor.whiteColor())
    lbl_title.setFont_(AppKit.NSFont.boldSystemFontOfSize_(13))
    lbl_title.setAlignment_(AppKit.NSTextAlignmentCenter)
    lbl_title.setFrame_(AppKit.NSMakeRect(10, 28, banner_w - 24, 20))
    inner.addSubview_(lbl_title)

    lbl_sub = AppKit.NSTextField.labelWithString_(
        "仅锁定此目标窗口 · 点击外部可随时切换，点回此页按 Esc 退出"
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
            state["is_locked_now"] = False
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
            state["is_locked_now"] = False
            hide_all()
            AppHelper.stopEventLoop()
            return

        if state_file.exists():
            try:
                st = json.loads(state_file.read_text(encoding="utf-8"))
                new_t = str(st.get("target") or "").strip()
                raw_pid = st.get("target_pid")
                raw_wid = st.get("target_wid")
                new_pid = int(raw_pid) if raw_pid else None
                new_wid = int(raw_wid) if raw_wid else None

                if new_t == "" and new_pid is None and new_wid is None:
                    state["target"] = ""
                    state["target_pid"] = None
                    state["target_wid"] = None
                    state["is_locked_now"] = False
                    state["bounds"] = None
                else:
                    changed = False
                    if new_t != state["target"]:
                        state["target"] = new_t
                        if new_pid is None and new_wid is None:
                            state["target_pid"] = None
                            state["target_wid"] = None
                        changed = True
                    if new_pid is not None and new_pid != state["target_pid"]:
                        state["target_pid"] = new_pid
                        changed = True
                    if new_wid is not None and new_wid != state["target_wid"]:
                        state["target_wid"] = new_wid
                        changed = True
                    if changed:
                        lbl_title.setStringValue_(_title_text(state["target"]))
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

    AppKit.NSTimer.scheduledTimerWithTimeInterval_repeats_block_(0.06, True, update_banner)

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

        # 2. Must have a bound target and be actively locked right now
        t_pid = state["target_pid"]
        if not t_pid or not state["is_locked_now"]:
            return event

        # 3. Live check frontmost app PID to avoid drift during timer interval
        front_app = _frontmost_app()
        if not front_app or int(front_app.processIdentifier()) != t_pid:
            return event

        # 4. Keyboard events inside bound window
        if event_type in (Quartz.kCGEventKeyDown, Quartz.kCGEventKeyUp):
            keycode = Quartz.CGEventGetIntegerValueField(event, Quartz.kCGKeyboardEventKeycode)
            flags = Quartz.CGEventGetFlags(event)
            # Allow Command+Tab (48) and Command+~ (50) for switching apps/windows
            if (flags & Quartz.kCGEventFlagMaskCommand) and keycode in (48, 50):
                return event
            if event_type == Quartz.kCGEventKeyDown and keycode == 53:  # Esc
                try:
                    abort_file.write_text("esc", encoding="utf-8")
                except Exception:
                    pass
                state["is_locked_now"] = False
                hide_all()
                AppHelper.stopEventLoop()
                return None
            return None

        # 5. Mouse click/drag/scroll: ONLY block inside the bound window rectangle
        pt = Quartz.CGEventGetLocation(event)
        if not _point_inside_target(pt):
            return event

        return None

    # kCGEventMouseMoved intentionally excluded so cursor movement is never blocked
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
    parser.add_argument("--target-pid", type=int, default=0)
    parser.add_argument("--target-wid", type=int, default=0)
    parser.add_argument("--timeout", type=float, default=45.0)
    args = parser.parse_args()
    run_guard(
        Path(args.state_dir),
        args.target,
        args.target_pid,
        args.target_wid,
        args.timeout,
    )


if __name__ == "__main__":
    main()
