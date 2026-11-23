#!/usr/bin/env python3
"""Ultra-fast single-process native MCP server for Antigravity Computer Use (v0.2.0)."""
from __future__ import annotations

import base64
import io
import json
import platform
import sys
import time
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import guard as guard_mod  # noqa: E402

SERVER_NAME = "antigravity-computer-use"
SERVER_VERSION = "0.2.2"
GUARD_TIMEOUT = 45.0

ABORT_MESSAGE = (
    "ABORTED_BY_USER: 用户已按 Esc 终止 AI 桌面操作。"
    "请立即停止后续操作并向用户汇报。"
)

_input_mod = None
_mss_mod = None
_pil_image_cls = None

_coord_space: dict[str, int] | None = None
_current_target: str = ""
_current_target_pid: int | None = None
_current_target_wid: int | None = None
_abort_cooldown_until: float = 0.0


def _get_input():
    global _input_mod
    if _input_mod is None:
        sys_name = platform.system()
        if sys_name == "Windows":
            import input_win as mod
        elif sys_name == "Darwin":
            import input_mac as mod
        else:
            raise RuntimeError(f"Unsupported OS: {sys_name}")
        _input_mod = mod
    return _input_mod


def _get_capture_libs():
    global _mss_mod, _pil_image_cls
    if _mss_mod is None or _pil_image_cls is None:
        import mss
        from PIL import Image
        _mss_mod = mss
        _pil_image_cls = Image
    return _mss_mod, _pil_image_cls


def _init_coord_space(max_width: int = 1024) -> dict[str, int]:
    global _coord_space
    mss, _ = _get_capture_libs()
    with mss.mss() as sct:
        mon = sct.monitors[0]
        mw = max(1, int(mon["width"]))
        mh = max(1, int(mon["height"]))
        ml = int(mon["left"])
        mt = int(mon["top"])
    if mw > max_width:
        iw = int(max_width)
        ih = max(1, int(round(mh * max_width / mw)))
    else:
        iw, ih = mw, mh
    _coord_space = {
        "mon_left": ml,
        "mon_top": mt,
        "mon_w": mw,
        "mon_h": mh,
        "img_w": iw,
        "img_h": ih,
    }
    return _coord_space


def _map_point(x: float | int, y: float | int) -> tuple[int, int]:
    cs = _coord_space or _init_coord_space()
    px = cs["mon_left"] + int(round(float(x) * cs["mon_w"] / max(1, cs["img_w"])))
    py = cs["mon_top"] + int(round(float(y) * cs["mon_h"] / max(1, cs["img_h"])))
    return px, py


def _clear_target_binding() -> None:
    global _current_target, _current_target_pid, _current_target_wid
    _current_target = ""
    _current_target_pid = None
    _current_target_wid = None


def _bind_from_window_info(win_info: Any) -> str:
    global _current_target, _current_target_pid, _current_target_wid
    if isinstance(win_info, dict):
        _current_target = str(win_info.get("title") or "")
        pid = win_info.get("pid")
        wid = win_info.get("window_id")
        _current_target_pid = int(pid) if pid else None
        _current_target_wid = int(wid) if wid else None
    elif isinstance(win_info, str):
        _current_target = win_info
        _current_target_pid = None
        _current_target_wid = None
    return _current_target


def _check_and_handle_abort() -> bool:
    global _abort_cooldown_until
    if guard_mod.ABORT_FILE.exists():
        guard_mod.ABORT_FILE.unlink(missing_ok=True)
        _abort_cooldown_until = time.time() + 5.0
        _clear_target_binding()
        guard_mod.stop_guard(quiet=True)
        return True
    if time.time() < _abort_cooldown_until:
        return True
    return False


def _ensure_guard_active() -> None:
    was_running = guard_mod.is_guard_running()
    guard_mod.start_guard(
        target=_current_target,
        timeout=GUARD_TIMEOUT,
        quiet=True,
        target_pid=_current_target_pid,
        target_wid=_current_target_wid,
    )
    if not was_running:
        time.sleep(0.15)


def _ensure_mac_bound_for_point(px: int | None = None, py: int | None = None) -> None:
    if platform.system() != "Darwin":
        return
    if _current_target_wid is not None and _current_target_pid is not None:
        return
    inp = _get_input()
    win = None
    if px is not None and py is not None:
        win = inp.window_at_point(px, py)
    if win is None:
        win = inp.frontmost_window()
    if win is not None:
        _bind_from_window_info(win)


# --- Tool implementations ---

def tool_take_screenshot(max_width: int = 1024, quality: int = 75) -> list[dict[str, Any]]:
    global _coord_space
    mss, PILImage = _get_capture_libs()
    max_width = max(320, min(3840, int(max_width)))
    quality = max(20, min(95, int(quality)))

    with mss.mss() as sct:
        mon = sct.monitors[0]
        raw = sct.grab(mon)
        pil_img = PILImage.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
        mw = max(1, int(mon["width"]))
        mh = max(1, int(mon["height"]))
        ml = int(mon["left"])
        mt = int(mon["top"])

    if pil_img.width > max_width:
        scale = max_width / float(pil_img.width)
        new_h = max(1, int(round(pil_img.height * scale)))
        pil_img = pil_img.resize((max_width, new_h), PILImage.Resampling.BILINEAR)

    _coord_space = {
        "mon_left": ml,
        "mon_top": mt,
        "mon_w": mw,
        "mon_h": mh,
        "img_w": pil_img.width,
        "img_h": pil_img.height,
    }

    buf = io.BytesIO()
    pil_img.save(buf, format="JPEG", quality=quality, optimize=False)
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")

    return [
        {"type": "image", "data": b64, "mimeType": "image/jpeg"},
        {
            "type": "text",
            "text": (
                f"Screenshot v0.2.2 {pil_img.width}x{pil_img.height} JPEG "
                f"(desktop={mw}x{mh}, origin=({ml},{mt})). "
                "Pass image pixel coordinates directly to mouse tools."
            ),
        },
    ]


def tool_get_screen_size() -> list[dict[str, Any]]:
    cs = _coord_space or _init_coord_space()
    return [
        {
            "type": "text",
            "text": json.dumps(
                {
                    "width": cs["img_w"],
                    "height": cs["img_h"],
                    "desktop_width": cs["mon_w"],
                    "desktop_height": cs["mon_h"],
                    "origin": [cs["mon_left"], cs["mon_top"]],
                    "message": f"Coordinate space: {cs['img_w']}x{cs['img_h']} (desktop {cs['mon_w']}x{cs['mon_h']})",
                },
                ensure_ascii=False,
            ),
        }
    ]


def tool_list_windows() -> list[dict[str, Any]]:
    wins = _get_input().list_windows()
    return [{"type": "text", "text": json.dumps(wins, ensure_ascii=False)}]


def tool_activate_window(title_pattern: str, use_regex: bool = False) -> list[dict[str, Any]]:
    matched = _get_input().activate_window(title_pattern, use_regex=use_regex)
    title = _bind_from_window_info(matched)
    _ensure_guard_active()
    return [{"type": "text", "text": f"Activated window: {title}"}]


def tool_click_screen(x: int, y: int, button: str = "left", clicks: int = 1) -> list[dict[str, Any]]:
    px, py = _map_point(x, y)
    _get_input().click(px, py, button=button, clicks=clicks)
    return [{"type": "text", "text": f"Clicked ({x}, {y}) -> ({px}, {py}) button={button} clicks={clicks}"}]


def tool_move_mouse(x: int, y: int) -> list[dict[str, Any]]:
    px, py = _map_point(x, y)
    _get_input().move_mouse(px, py)
    return [{"type": "text", "text": f"Moved to ({x}, {y}) -> ({px}, {py})"}]


def tool_drag_mouse(
    from_x: int,
    from_y: int,
    to_x: int,
    to_y: int,
    duration: float = 0.25,
    button: str = "left",
) -> list[dict[str, Any]]:
    px1, py1 = _map_point(from_x, from_y)
    px2, py2 = _map_point(to_x, to_y)
    _get_input().drag(px1, py1, px2, py2, duration=duration, button=button)
    return [{"type": "text", "text": f"Dragged ({from_x},{from_y})->({to_x},{to_y})"}]


def tool_scroll(clicks: int, x: int | None = None, y: int | None = None) -> list[dict[str, Any]]:
    if x is not None and y is not None:
        px, py = _map_point(x, y)
    else:
        px, py = None, None
    _get_input().scroll(clicks=int(clicks), x=px, y=py)
    return [{"type": "text", "text": f"Scrolled {clicks} clicks"}]


def tool_type_text(text: str) -> list[dict[str, Any]]:
    _get_input().type_text(str(text))
    return [{"type": "text", "text": f"Typed {len(text)} chars"}]


def tool_press_keys(keys: Any) -> list[dict[str, Any]]:
    _get_input().press_keys(keys)
    return [{"type": "text", "text": f"Pressed keys: {keys!r}"}]


def tool_execute_actions(
    actions: list[dict[str, Any]],
    release_after: bool = False,
) -> tuple[list[dict[str, Any]], bool]:
    global _current_target
    inp = _get_input()
    results: list[dict[str, Any]] = []

    for idx, act in enumerate(actions):
        if _check_and_handle_abort():
            return [{"type": "text", "text": ABORT_MESSAGE}], True

        guard_mod.write_heartbeat()
        kind = str(act.get("type") or act.get("action") or "").strip().lower()

        if kind in ("click", "click_screen"):
            px, py = _map_point(act["x"], act["y"])
            _ensure_mac_bound_for_point(px, py)
            _ensure_guard_active()
            inp.click(px, py, button=str(act.get("button", "left")), clicks=int(act.get("clicks", 1)))
            results.append({"index": idx, "action": kind, "ok": True})
        elif kind == "double_click":
            px, py = _map_point(act["x"], act["y"])
            _ensure_mac_bound_for_point(px, py)
            _ensure_guard_active()
            inp.click(px, py, button=str(act.get("button", "left")), clicks=2)
            results.append({"index": idx, "action": kind, "ok": True})
        elif kind == "right_click":
            px, py = _map_point(act["x"], act["y"])
            _ensure_mac_bound_for_point(px, py)
            _ensure_guard_active()
            inp.click(px, py, button="right", clicks=1)
            results.append({"index": idx, "action": kind, "ok": True})
        elif kind in ("move", "move_mouse"):
            px, py = _map_point(act["x"], act["y"])
            _ensure_mac_bound_for_point(px, py)
            _ensure_guard_active()
            inp.move_mouse(px, py)
            results.append({"index": idx, "action": kind, "ok": True})
        elif kind in ("drag", "drag_mouse"):
            px1, py1 = _map_point(act["from_x"], act["from_y"])
            px2, py2 = _map_point(act["to_x"], act["to_y"])
            _ensure_mac_bound_for_point(px1, py1)
            _ensure_guard_active()
            inp.drag(px1, py1, px2, py2, duration=float(act.get("duration", 0.25)), button=str(act.get("button", "left")))
            results.append({"index": idx, "action": kind, "ok": True})
        elif kind == "scroll":
            cx = act.get("x")
            cy = act.get("y")
            px, py = _map_point(cx, cy) if (cx is not None and cy is not None) else (None, None)
            _ensure_mac_bound_for_point(px, py)
            _ensure_guard_active()
            inp.scroll(clicks=int(act.get("clicks", 0)), x=px, y=py)
            results.append({"index": idx, "action": kind, "ok": True})
        elif kind in ("type", "type_text", "write"):
            _ensure_mac_bound_for_point()
            _ensure_guard_active()
            inp.type_text(str(act.get("text", "")))
            results.append({"index": idx, "action": kind, "ok": True})
        elif kind in ("press", "press_keys", "hotkey"):
            _ensure_mac_bound_for_point()
            _ensure_guard_active()
            inp.press_keys(act.get("keys", act.get("key")))
            results.append({"index": idx, "action": kind, "ok": True})
        elif kind in ("wait", "sleep", "wait_milliseconds"):
            ms = act.get("milliseconds", act.get("ms"))
            sec = max(0.0, float(ms) / 1000.0) if ms is not None else max(0.0, float(act.get("seconds", 0.0)))
            end = time.time() + sec
            while time.time() < end:
                if _check_and_handle_abort():
                    return [{"type": "text", "text": ABORT_MESSAGE}], True
                time.sleep(min(0.05, max(0.0, end - time.time())))
            results.append({"index": idx, "action": kind, "ok": True})
        elif kind == "activate_window":
            tp = str(act.get("title_pattern", act.get("title", "")))
            matched = inp.activate_window(tp, use_regex=bool(act.get("use_regex", False)))
            title = _bind_from_window_info(matched)
            _ensure_guard_active()
            results.append({"index": idx, "action": kind, "ok": True, "window": title})
        else:
            raise ValueError(f"Unknown action type: {kind!r}")

    if release_after:
        _clear_target_binding()
        guard_mod.stop_guard(quiet=True)

    return [{"type": "text", "text": json.dumps({"success": True, "released": release_after, "results": results}, ensure_ascii=False)}], False


def tool_release_control() -> list[dict[str, Any]]:
    _clear_target_binding()
    guard_mod.stop_guard(quiet=True)
    return [{"type": "text", "text": "Released AI Guard lock and closed overlay."}]


TOOLS_SPEC: list[dict[str, Any]] = [
    {
        "name": "take_screenshot",
        "description": "Capture desktop screenshot as fast scaled JPEG image. Automatically enables AI Guard lock.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "max_width": {"type": "integer", "default": 1024, "description": "Max output width in pixels"},
                "quality": {"type": "integer", "default": 75, "description": "JPEG quality (20-95)"},
            },
        },
    },
    {
        "name": "get_screen_size",
        "description": "Get current screenshot coordinate space dimensions and desktop resolution.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "list_windows",
        "description": "List visible desktop windows with title, bounds and active status.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "activate_window",
        "description": "Bring a matching window to foreground and set it as AI Guard target.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title_pattern": {"type": "string", "description": "Substring or regex matching window title"},
                "use_regex": {"type": "boolean", "default": False},
            },
            "required": ["title_pattern"],
        },
    },
    {
        "name": "click_screen",
        "description": "Click at (x, y) in screenshot coordinate space.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "x": {"type": "integer"},
                "y": {"type": "integer"},
                "button": {"type": "string", "enum": ["left", "right", "middle"], "default": "left"},
                "clicks": {"type": "integer", "default": 1},
            },
            "required": ["x", "y"],
        },
    },
    {
        "name": "move_mouse",
        "description": "Move cursor to (x, y) in screenshot coordinate space.",
        "inputSchema": {
            "type": "object",
            "properties": {"x": {"type": "integer"}, "y": {"type": "integer"}},
            "required": ["x", "y"],
        },
    },
    {
        "name": "drag_mouse",
        "description": "Drag mouse from (from_x, from_y) to (to_x, to_y) in screenshot coordinate space.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "from_x": {"type": "integer"},
                "from_y": {"type": "integer"},
                "to_x": {"type": "integer"},
                "to_y": {"type": "integer"},
                "duration": {"type": "number", "default": 0.25},
                "button": {"type": "string", "enum": ["left", "right", "middle"], "default": "left"},
            },
            "required": ["from_x", "from_y", "to_x", "to_y"],
        },
    },
    {
        "name": "scroll",
        "description": "Scroll wheel (positive=up, negative=down), optionally moving to (x, y) first.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "clicks": {"type": "integer"},
                "x": {"type": "integer"},
                "y": {"type": "integer"},
            },
            "required": ["clicks"],
        },
    },
    {
        "name": "type_text",
        "description": "Type Unicode text (supports Chinese/English directly, bypassing IME issues).",
        "inputSchema": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
    },
    {
        "name": "press_keys",
        "description": "Press a key, hotkey string (e.g. 'ctrl+v', 'command+v'), or list of keys.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "keys": {"description": "String like 'enter' or 'ctrl+c', or array like ['ctrl', 'v']"},
            },
            "required": ["keys"],
        },
    },
    {
        "name": "execute_actions",
        "description": "Execute a batch of actions sequentially (checks Esc abort before every step).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "actions": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "List of action objects with 'type' (click, double_click, right_click, move, drag, scroll, type, press, hotkey, wait, activate_window)",
                },
                "release_after": {
                    "type": "boolean",
                    "default": False,
                    "description": "If true, immediately release AI Guard lock once all actions succeed (saves an extra release_control turn).",
                },
            },
            "required": ["actions"],
        },
    },
    {
        "name": "release_control",
        "description": "Immediately stop AI Guard overlay and unlock user mouse/keyboard.",
        "inputSchema": {"type": "object", "properties": {}},
    },
]

GUARDED_TOOLS = {
    "take_screenshot",
    "activate_window",
    "click_screen",
    "move_mouse",
    "drag_mouse",
    "scroll",
    "type_text",
    "press_keys",
    "execute_actions",
}


def _dispatch_tool(name: str, args: dict[str, Any]) -> tuple[list[dict[str, Any]], bool]:
    global _current_target

    if name == "release_control":
        return tool_release_control(), False
    if name == "get_screen_size":
        if guard_mod.is_guard_running():
            guard_mod.write_heartbeat()
        return tool_get_screen_size(), False
    if name == "list_windows":
        if guard_mod.is_guard_running():
            guard_mod.write_heartbeat()
        return tool_list_windows(), False

    if name in GUARDED_TOOLS:
        if _check_and_handle_abort():
            return [{"type": "text", "text": ABORT_MESSAGE}], True
        if name == "take_screenshot":
            if platform.system() != "Darwin" or _current_target_wid is not None or _current_target != "":
                _ensure_guard_active()
        elif name in ("click_screen", "move_mouse"):
            px, py = _map_point(args["x"], args["y"])
            _ensure_mac_bound_for_point(px, py)
            _ensure_guard_active()
        elif name == "drag_mouse":
            px, py = _map_point(args["from_x"], args["from_y"])
            _ensure_mac_bound_for_point(px, py)
            _ensure_guard_active()
        elif name == "scroll":
            if args.get("x") is not None and args.get("y") is not None:
                px, py = _map_point(args["x"], args["y"])
            else:
                px, py = None, None
            _ensure_mac_bound_for_point(px, py)
            _ensure_guard_active()
        elif name in ("type_text", "press_keys"):
            _ensure_mac_bound_for_point()
            _ensure_guard_active()
        elif name == "execute_actions" and platform.system() != "Darwin":
            for act in args.get("actions") or []:
                if isinstance(act, dict) and str(act.get("type") or act.get("action") or "").strip().lower() == "activate_window":
                    tp = act.get("title_pattern") or act.get("title")
                    if tp:
                        _bind_from_window_info(str(tp))
                        break
            _ensure_guard_active()

    try:
        if name == "take_screenshot":
            content = tool_take_screenshot(
                max_width=args.get("max_width", 1024),
                quality=args.get("quality", 75),
            )
            is_err = False
        elif name == "activate_window":
            content = tool_activate_window(
                title_pattern=str(args["title_pattern"]),
                use_regex=bool(args.get("use_regex", False)),
            )
            is_err = False
        elif name == "click_screen":
            content = tool_click_screen(
                x=int(args["x"]),
                y=int(args["y"]),
                button=str(args.get("button", "left")),
                clicks=int(args.get("clicks", 1)),
            )
            is_err = False
        elif name == "move_mouse":
            content = tool_move_mouse(x=int(args["x"]), y=int(args["y"]))
            is_err = False
        elif name == "drag_mouse":
            content = tool_drag_mouse(
                from_x=int(args["from_x"]),
                from_y=int(args["from_y"]),
                to_x=int(args["to_x"]),
                to_y=int(args["to_y"]),
                duration=float(args.get("duration", 0.25)),
                button=str(args.get("button", "left")),
            )
            is_err = False
        elif name == "scroll":
            content = tool_scroll(
                clicks=int(args["clicks"]),
                x=args.get("x"),
                y=args.get("y"),
            )
            is_err = False
        elif name == "type_text":
            content = tool_type_text(text=str(args["text"]))
            is_err = False
        elif name == "press_keys":
            content = tool_press_keys(keys=args["keys"])
            is_err = False
        elif name == "execute_actions":
            content, is_err = tool_execute_actions(
                actions=list(args.get("actions") or []),
                release_after=bool(args.get("release_after", False)),
            )
        else:
            content = [{"type": "text", "text": f"Unknown tool: {name}"}]
            is_err = True
    finally:
        if name in GUARDED_TOOLS and guard_mod.is_guard_running():
            guard_mod.write_heartbeat()

    return content, is_err


def _write_msg(obj: dict[str, Any]) -> None:
    line = (json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8")
    sys.stdout.buffer.write(line)
    sys.stdout.buffer.flush()


def main() -> int:
    try:
        while True:
            raw = sys.stdin.buffer.readline()
            if not raw:
                break
            stripped = raw.strip()
            if not stripped:
                continue

            try:
                req = json.loads(stripped.decode("utf-8"))
            except Exception as exc:
                _write_msg({
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32700, "message": f"Parse error: {exc}"},
                })
                continue

            req_id = req.get("id")
            method = req.get("method", "")
            params = req.get("params") or {}

            # Notifications have no id -> do not reply
            if req_id is None:
                continue

            if method == "initialize":
                proto = params.get("protocolVersion") or "2024-11-05"
                _write_msg({
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "protocolVersion": proto,
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                    },
                })
            elif method == "ping":
                _write_msg({"jsonrpc": "2.0", "id": req_id, "result": {}})
            elif method == "tools/list":
                _write_msg({"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS_SPEC}})
            elif method == "tools/call":
                t_name = str(params.get("name") or "")
                t_args = params.get("arguments") or {}
                try:
                    content, is_err = _dispatch_tool(t_name, t_args)
                except Exception as exc:
                    content = [{"type": "text", "text": f"Tool error ({t_name}): {exc}"}]
                    is_err = True
                _write_msg({
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {"content": content, "isError": is_err},
                })
            else:
                _write_msg({
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32601, "message": f"Method not found: {method}"},
                })
    except Exception as exc:
        print(f"[server] fatal: {exc}", file=sys.stderr, flush=True)
        return 1
    finally:
        guard_mod.stop_guard(quiet=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
