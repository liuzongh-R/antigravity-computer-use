#!/usr/bin/env python3
"""Transparent stdio MCP proxy with automatic AI Guard and instant Esc abort."""
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

READONLY_TOOLS = {
    "take_screenshot",
    "take_screenshot_with_ocr",
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


def _is_guard_running() -> bool:
    if not guard_mod.PID_FILE.exists():
        return False
    try:
        pid = int(guard_mod.PID_FILE.read_text(encoding="utf-8").strip())
        return guard_mod.is_pid_alive(pid)
    except Exception:
        return False


def _update_state_target(target: str, timeout: float) -> None:
    guard_mod.ensure_state_dir()
    data = {
        "target": target,
        "started_at": time.time(),
        "os": platform.system(),
        "timeout": timeout,
    }
    if guard_mod.STATE_FILE.exists():
        try:
            old = json.loads(guard_mod.STATE_FILE.read_text(encoding="utf-8"))
            if isinstance(old, dict):
                old["target"] = target
                old["timeout"] = timeout
                data = old
        except Exception:
            pass
    guard_mod.STATE_FILE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _call_guard_script(*args: str) -> None:
    guard_py = HERE / "guard.py"
    try:
        subprocess.run(
            [sys.executable, str(guard_py), *args],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
            **_no_window_kwargs(),
        )
    except Exception:
        pass


def _ensure_guard_started(target: str, timeout: float, uvx_path: str) -> None:
    guard_mod.write_heartbeat()
    if _is_guard_running():
        _update_state_target(target, timeout)
        return
    _call_guard_script(
        "start",
        "--target",
        target,
        "--timeout",
        str(timeout),
        "--uvx",
        uvx_path,
    )


def _stop_guard() -> None:
    _call_guard_script("stop")


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


def _parse_cli(argv: list[str]) -> tuple[str, float, list[str]]:
    if "--" in argv:
        idx = argv.index("--")
        proxy_argv = argv[:idx]
        mcp_args = argv[idx + 1 :]
    else:
        proxy_argv = argv
        mcp_args = []

    parser = argparse.ArgumentParser()
    parser.add_argument("--uvx", required=True)
    parser.add_argument("--timeout", type=float, default=20.0)
    args, extra = parser.parse_known_args(proxy_argv)
    if not mcp_args:
        mcp_args = extra
    return args.uvx, args.timeout, mcp_args


def main() -> int:
    uvx_path, timeout, mcp_args = _parse_cli(sys.argv[1:])
    if not mcp_args:
        mcp_args = ["computer-control-mcp@latest"]

    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"

    proc = subprocess.Popen(
        [uvx_path, *mcp_args],
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
                    _stop_guard()
                    _send_abort_response(req.get("id"), stdout_lock)
                    forward = False
                elif tool_name in ACTION_TOOLS and time.time() < abort_cooldown_until:
                    _send_abort_response(req.get("id"), stdout_lock)
                    forward = False
                elif tool_name in ACTION_TOOLS:
                    if tool_name == "activate_window":
                        tp = arguments.get("title_pattern")
                        if tp:
                            current_target = str(tp)
                    _ensure_guard_started(current_target, timeout, uvx_path)
                elif tool_name in READONLY_TOOLS:
                    if _is_guard_running():
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
        _stop_guard()

    return proc.returncode or 0


if __name__ == "__main__":
    raise SystemExit(main())
