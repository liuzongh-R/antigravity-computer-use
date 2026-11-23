#!/usr/bin/env python3
"""macOS AI Computer-Use Guard (v0.2.3):
- Zero drag lag: tracks frontmost PID via NSWorkspaceDidActivateApplicationNotification
  (zero PyObjC IPC inside CGEventTap callback) and excludes MouseMoved/MouseDragged.
- Background window visibility: keeps soft ice-blue rounded glow border & frosted
  glass pill anchored directly above target_wid (NSNormalWindowLevel + NSWindowAbove)
  so it stays visible even when behind other apps, without covering foreground apps.
- Strict single-window lock: only intercepts clicks/scrolls inside target_wid and
  non-Esc keys when target_wid is top-frontmost.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time

AI_MAGIC_TAG = 0x41475943  # 'AGYC'
GLOW_PAD = 12.0


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

    init_front = AppKit.NSWorkspace.sharedWorkspace().frontmostApplication()
    state = {
        "target": target.strip(),
        "target_pid": target_pid if target_pid > 0 else None,
        "target_wid": target_wid if target_wid > 0 else None,
        "front_pid": int(init_front.processIdentifier()) if init_front else 0,
        "bounds": None,
        "last_drawn_bounds": None,
        "is_locked_now": False,
        "logged_key": None,
    }

    def _on_app_activate(notif) -> None:
        try:
            info = notif.userInfo()
            if info:
                activated = info.get(AppKit.NSWorkspaceApplicationKey)
                if activated:
                    state["front_pid"] = int(activated.processIdentifier())
        except Exception:
            pass

    ws_nc = AppKit.NSWorkspace.sharedWorkspace().notificationCenter()
    observer = ws_nc.addObserverForName_object_queue_usingBlock_(
        AppKit.NSWorkspaceDidActivateApplicationNotification,
        None,
        None,
        _on_app_activate,
    )

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

    def refresh_target_window() -> tuple[bool, bool, dict | None]:
        """Returns (is_visible_on_screen, is_top_frontmost, bounds)."""
        if state["target_pid"] is None and state["target_wid"] is None and not state["target"]:
            state["is_locked_now"] = False
            state["bounds"] = None
            return False, False, None

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
            return False, False, None

        target_win = None
        top_pid_wid = None
        for w in windows:
            if w.get("kCGWindowLayer", 0) != 0:
                continue
            b = w.get("kCGWindowBounds")
            if not b or b.get("Width", 0) <= 100 or b.get("Height", 0) <= 60:
                continue
            wpid = int(w.get("kCGWindowOwnerPID") or 0)
            wwid = int(w.get("kCGWindowNumber") or 0)

            if t_pid is not None and wpid == t_pid and top_pid_wid is None:
                top_pid_wid = wwid

            if t_wid is not None and wwid == t_wid:
                target_win = w
                if state["target_pid"] is None and wpid > 0:
                    state["target_pid"] = wpid
                break
            if t_wid is None and t_pid is not None and wpid == t_pid:
                target_win = w
                state["target_wid"] = wwid
                _log_binding_if_changed()
                break

        if target_win is None:
            state["is_locked_now"] = False
            state["bounds"] = None
            return False, False, None

        b = target_win["kCGWindowBounds"]
        bounds = {
            "X": float(b["X"]),
            "Y": float(b["Y"]),
            "Width": float(b["Width"]),
            "Height": float(b["Height"]),
        }
        state["bounds"] = bounds

        t_pid = state["target_pid"]
        t_wid = state["target_wid"]
        is_front_app = (t_pid is not None and state["front_pid"] == t_pid)
        is_top_window = is_front_app and (top_pid_wid == t_wid)
        state["is_locked_now"] = is_top_window
        return True, is_top_window, bounds

    def primary_screen_height() -> float:
        screens = AppKit.NSScreen.screens()
        if screens and len(screens) > 0:
            return float(screens[0].frame().size.height)
        main = AppKit.NSScreen.mainScreen()
        return float(main.frame().size.height) if main else 900.0

    def _make_overlay_panel(w: float, h: float) -> object:
        p = AppKit.NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            AppKit.NSMakeRect(0, 0, w, h),
            AppKit.NSWindowStyleMaskBorderless | AppKit.NSWindowStyleMaskNonactivatingPanel,
            AppKit.NSBackingStoreBuffered,
            False,
        )
        # Normal window level so we can anchor strictly above target_wid without covering other foreground apps
        p.setLevel_(AppKit.NSNormalWindowLevel)
        p.setOpaque_(False)
        p.setHasShadow_(False)
        p.setBackgroundColor_(AppKit.NSColor.clearColor())
        p.setIgnoresMouseEvents_(True)
        return p

    app = AppKit.NSApplication.sharedApplication()
    app.setActivationPolicy_(AppKit.NSApplicationActivationPolicyAccessory)

    # 1. Single-panel rounded glowing ice-blue border (matches macOS 11pt window radius)
    border_panel = _make_overlay_panel(300.0, 200.0)
    border_root = AppKit.NSView.alloc().initWithFrame_(AppKit.NSMakeRect(0, 0, 300.0, 200.0))
    border_root.setWantsLayer_(True)
    border_root.layer().setBackgroundColor_(AppKit.NSColor.clearColor().CGColor())
    border_root.layer().setMasksToBounds_(False)
    border_panel.setContentView_(border_root)

    glow_view = AppKit.NSView.alloc().initWithFrame_(
        AppKit.NSMakeRect(GLOW_PAD, GLOW_PAD, 300.0 - 2 * GLOW_PAD, 200.0 - 2 * GLOW_PAD)
    )
    glow_view.setWantsLayer_(True)
    gl = glow_view.layer()
    gl.setBackgroundColor_(AppKit.NSColor.clearColor().CGColor())
    gl.setCornerRadius_(11.0)
    gl.setBorderWidth_(2.0)
    gl.setBorderColor_(
        AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(0.49, 0.83, 0.99, 0.86).CGColor()
    )
    gl.setShadowColor_(
        AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(0.22, 0.74, 0.97, 0.95).CGColor()
    )
    gl.setShadowOpacity_(0.85)
    gl.setShadowRadius_(8.5)
    gl.setShadowOffset_((0.0, 0.0))
    gl.setMasksToBounds_(False)
    border_root.addSubview_(glow_view)

    # 2. High-contrast dark frosted glass floating pill banner (legible on light & dark backgrounds)
    pill_w, pill_h = 432.0, 38.0
    pill_panel = _make_overlay_panel(pill_w, pill_h)
    try:
        dark_app = AppKit.NSAppearance.appearanceNamed_(AppKit.NSAppearanceNameVibrantDark)
        if dark_app is not None:
            pill_panel.setAppearance_(dark_app)
    except Exception:
        pass

    vfx = AppKit.NSVisualEffectView.alloc().initWithFrame_(AppKit.NSMakeRect(0, 0, pill_w, pill_h))
    vfx.setMaterial_(AppKit.NSVisualEffectMaterialHUDWindow)
    vfx.setBlendingMode_(AppKit.NSVisualEffectBlendingModeBehindWindow)
    vfx.setState_(AppKit.NSVisualEffectStateActive)
    vfx.setWantsLayer_(True)
    vl = vfx.layer()
    vl.setCornerRadius_(17.0)
    vl.setMasksToBounds_(True)
    vl.setBackgroundColor_(
        AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(0.05, 0.08, 0.15, 0.86).CGColor()
    )
    vl.setBorderWidth_(1.2)
    vl.setBorderColor_(
        AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(0.55, 0.85, 1.0, 0.72).CGColor()
    )
    pill_panel.setContentView_(vfx)

    dot_lbl = AppKit.NSTextField.labelWithString_("●")
    dot_lbl.setTextColor_(
        AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(0.49, 0.85, 1.0, 1.0)
    )
    dot_lbl.setFont_(AppKit.NSFont.boldSystemFontOfSize_(12))
    dot_lbl.setFrame_(AppKit.NSMakeRect(14, 11, 16, 16))
    vfx.addSubview_(dot_lbl)

    def _short_title(t: str) -> str:
        t = (t or "目标窗口").strip()
        if len(t) > 15:
            t = t[:14] + "…"
        return f"AI 正在操控 {t}"

    lbl_title = AppKit.NSTextField.labelWithString_(_short_title(state["target"]))
    lbl_title.setTextColor_(AppKit.NSColor.whiteColor())
    lbl_title.setFont_(AppKit.NSFont.systemFontOfSize_weight_(13.0, AppKit.NSFontWeightSemibold))
    lbl_title.setFrame_(AppKit.NSMakeRect(30, 9, 240, 20))
    vfx.addSubview_(lbl_title)

    badge_view = AppKit.NSView.alloc().initWithFrame_(AppKit.NSMakeRect(276, 7, 142, 24))
    badge_view.setWantsLayer_(True)
    bl = badge_view.layer()
    bl.setCornerRadius_(10.0)
    bl.setBackgroundColor_(
        AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(0.22, 0.74, 0.97, 0.30).CGColor()
    )
    bl.setBorderWidth_(1.0)
    bl.setBorderColor_(
        AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(0.58, 0.86, 1.0, 0.65).CGColor()
    )
    vfx.addSubview_(badge_view)

    lbl_badge = AppKit.NSTextField.labelWithString_("点此页按 ESC 退出")
    lbl_badge.setTextColor_(
        AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(0.90, 0.96, 1.0, 1.0)
    )
    lbl_badge.setFont_(AppKit.NSFont.systemFontOfSize_weight_(11.5, AppKit.NSFontWeightSemibold))
    lbl_badge.setAlignment_(AppKit.NSTextAlignmentCenter)
    lbl_badge.setFrame_(AppKit.NSMakeRect(4, 3, 134, 18))
    badge_view.addSubview_(lbl_badge)

    def hide_all() -> None:
        border_panel.orderOut_(None)
        pill_panel.orderOut_(None)
        state["last_drawn_bounds"] = None

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
                        lbl_title.setStringValue_(_short_title(state["target"]))
                        state["last_drawn_bounds"] = None
            except Exception:
                pass

        is_visible, _, bounds = refresh_target_window()
        t_wid = state["target_wid"]
        if not is_visible or not bounds or not t_wid:
            hide_all()
            return

        bx = bounds["X"]
        by = bounds["Y"]
        bw = bounds["Width"]
        bh = bounds["Height"]
        b_key = (bx, by, bw, bh, t_wid)

        if b_key != state["last_drawn_bounds"]:
            sh = primary_screen_height()
            b_rect = AppKit.NSMakeRect(
                bx - GLOW_PAD,
                sh - (by + bh) - GLOW_PAD,
                bw + 2.0 * GLOW_PAD,
                bh + 2.0 * GLOW_PAD,
            )
            border_panel.setFrame_display_(b_rect, True)
            border_root.setFrame_(AppKit.NSMakeRect(0, 0, b_rect.size.width, b_rect.size.height))
            glow_view.setFrame_(AppKit.NSMakeRect(GLOW_PAD, GLOW_PAD, bw, bh))

            px = bx + max(8.0, (bw - pill_w) / 2.0)
            py = sh - by - pill_h - 10.0
            pill_panel.setFrameOrigin_(AppKit.NSMakePoint(px, py))
            state["last_drawn_bounds"] = b_key

        # Keep anchored strictly right above target_wid in Z-order (visible even behind other windows!)
        border_panel.orderWindow_relativeTo_(AppKit.NSWindowAbove, int(t_wid))
        pill_panel.orderWindow_relativeTo_(AppKit.NSWindowAbove, int(border_panel.windowNumber()))

    AppKit.NSTimer.scheduledTimerWithTimeInterval_repeats_block_(0.15, True, update_banner)

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

        # 2. Pure in-memory check (zero Objective-C IPC -> zero drag lag!)
        t_pid = state["target_pid"]
        if not t_pid or not state["is_locked_now"] or state["front_pid"] != t_pid:
            return event

        # 3. Keyboard events inside active bound window
        if event_type in (Quartz.kCGEventKeyDown, Quartz.kCGEventKeyUp):
            keycode = Quartz.CGEventGetIntegerValueField(event, Quartz.kCGKeyboardEventKeycode)
            flags = Quartz.CGEventGetFlags(event)
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

        # 4. Mouse click/scroll: ONLY block inside the bound window rectangle
        pt = Quartz.CGEventGetLocation(event)
        if not _point_inside_target(pt):
            return event

        return None

    # MouseMoved & MouseDragged are intentionally excluded for silky smooth window dragging
    mask = (
        Quartz.CGEventMaskBit(Quartz.kCGEventKeyDown)
        | Quartz.CGEventMaskBit(Quartz.kCGEventKeyUp)
        | Quartz.CGEventMaskBit(Quartz.kCGEventLeftMouseDown)
        | Quartz.CGEventMaskBit(Quartz.kCGEventLeftMouseUp)
        | Quartz.CGEventMaskBit(Quartz.kCGEventRightMouseDown)
        | Quartz.CGEventMaskBit(Quartz.kCGEventRightMouseUp)
        | Quartz.CGEventMaskBit(Quartz.kCGEventOtherMouseDown)
        | Quartz.CGEventMaskBit(Quartz.kCGEventOtherMouseUp)
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

    try:
        AppHelper.runEventLoop()
    finally:
        try:
            ws_nc.removeObserver_(observer)
        except Exception:
            pass


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
