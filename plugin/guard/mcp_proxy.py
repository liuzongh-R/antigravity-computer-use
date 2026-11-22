#!/usr/bin/env python3
"""Transparent stdio MCP proxy with direct venv backend, in-process Guard & instant Esc abort."""
from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import guard as guard_mod  # noqa: E402

ACTION_TOOLS = {
    "click_screen",
    "type_text",
    "press_keys",
    "execute_actions",
    "activate_window",
    "move_mouse",
    "mouse_down",
    "mouse_up",
    "drag_mouse",
    "key_down",
    "key_up",
    "wait_milliseconds",
}

GUARD_TRIGGER_TOOLS = ACTION_TOOLS | {
    "take_screenshot",
    "take_screenshot_with_ocr",
}

READONLY_TOOLS = {
    "list_windows",
    "get_screen_size",
}

ABORT_MESSAGE = (
    "ABORTED_BY_USER: 用户已按 Esc 终止 AI 桌面操作。"
    "请立即停止后续操作并向用户汇报。"
)


def _no_window_kwargs() -> dict:
    if platform.system() == "Windows":
        return {"creationflags": 0x08000000}  # CREATE_NO_WINDOW
    return {}


def _send_abort_response(req_id, stdout_lock: threading.Lock) -> None:
    if req_id is None:
        return
    resp = {
        "jsonrpc": "2.0",
        "id": req_id,
        "result": {
            "content": [{"type": "text", "text": ABORT_MESSAGE}],
            "isError": True,
        },
    }
    payload = (json.dumps(resp, ensure_ascii=False) + "\n").encode("utf-8")
    with stdout_lock:
        sys.stdout.buffer.write(payload)
        sys.stdout.buffer.flush()


def _forward_stream(src, dst, lock: threading.Lock | None = None) -> None:
    try:
        while True:
            line = src.readline()
            if not line:
                break
            if lock is not None:
                with lock:
                    dst.write(line)
                    dst.flush()
            else:
                dst.write(line)
                dst.flush()
    except Exception:
        pass


def _parse_cli(argv: list[str]) -> tuple[str, str, float, list[str]]:
    if "--" in argv:
        idx = argv.index("--")
        proxy_argv = argv[:idx]
        mcp_args = argv[idx + 1 :]
    else:
        proxy_argv = argv
        mcp_args = []

    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", default="")
    parser.add_argument("--uvx", default="")
    parser.add_argument("--timeout", type=float, default=20.0)
    args, extra = parser.parse_known_args(proxy_argv)
    if not mcp_args:
        mcp_args = extra
    return args.backend, args.uvx, args.timeout, mcp_args


def main() -> int:
    backend_path, uvx_path, timeout, mcp_args = _parse_cli(sys.argv[1:])

    if backend_path:
        backend_cmd = [backend_path, *mcp_args]
    elif uvx_path:
        if not mcp_args:
            mcp_args = ["computer-control-mcp@latest"]
        backend_cmd = [uvx_path, *mcp_args]
    else:
        sys.stderr.write("[mcp_proxy] missing --backend or --uvx\n")
        sys.stderr.flush()
        return 2

    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"

    proc = subprocess.Popen(
        backend_cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        **_no_window_kwargs(),
    )

    stdout_lock = threading.Lock()
    t_out = threading.Thread(
        target=_forward_stream,
        args=(proc.stdout, sys.stdout.buffer, stdout_lock),
        daemon=True,
    )
    t_err = threading.Thread(
        target=_forward_stream,
        args=(proc.stderr, sys.stderr.buffer, None),
        daemon=True,
    )
    t_out.start()
    t_err.start()

    current_target = ""
    abort_cooldown_until = 0.0

    try:
        while True:
            raw_line = sys.stdin.buffer.readline()
            if not raw_line:
                break

            stripped = raw_line.strip()
            if not stripped:
                continue

            forward = True
            try:
                req = json.loads(stripped.decode("utf-8"))
            except Exception:
                req = None

            if isinstance(req, dict) and req.get("method") == "tools/call":
                params = req.get("params") or {}
                tool_name = params.get("name", "")
                arguments = params.get("arguments") or {}

                if guard_mod.ABORT_FILE.exists():
                    try:
                        guard_mod.ABORT_FILE.unlink(missing_ok=True)
                    except Exception:
                        pass
                    abort_cooldown_until = time.time() + 5.0
                    guard_mod.stop_guard(quiet=True)
                    _send_abort_response(req.get("id"), stdout_lock)
                    forward = False
                elif tool_name in GUARD_TRIGGER_TOOLS and time.time() < abort_cooldown_until:
                    _send_abort_response(req.get("id"), stdout_lock)
                    forward = False
                elif tool_name in GUARD_TRIGGER_TOOLS:
                    if tool_name == "activate_window":
                        tp = arguments.get("title_pattern")
                        if tp:
                            current_target = str(tp)
                    elif tool_name == "take_screenshot_with_ocr" or tool_name == "take_screenshot":
                        tp = arguments.get("title_pattern")
                        if tp:
                            current_target = str(tp)
                    guard_mod.start_guard(
                        target=current_target,
                        timeout=timeout,
                        uvx_hint=uvx_path,
                        quiet=True,
                    )
                elif tool_name in READONLY_TOOLS:
                    if guard_mod.is_guard_running():
                        guard_mod.write_heartbeat()

            if forward:
                if proc.poll() is not None:
                    break
                assert proc.stdin is not None
                proc.stdin.write(raw_line)
                proc.stdin.flush()
    except Exception as exc:
        sys.stderr.write(f"[mcp_proxy] error: {exc}\n")
        sys.stderr.flush()
    finally:
        try:
            if proc.stdin:
                proc.stdin.close()
        except Exception:
            pass
        try:
            proc.wait(timeout=2)
        except Exception:
            try:
                proc.terminate()
                proc.wait(timeout=1)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        guard_mod.stop_guard(quiet=True)

    return proc.returncode or 0


if __name__ == "__main__":
    raise SystemExit(main())
