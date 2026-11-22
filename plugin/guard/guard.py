#!/usr/bin/env python3
"""Cross-platform AI Computer-Use Guard (Windows & macOS).

Usage:
  python guard.py start [--target "<app_or_window>"] [--timeout 20] [--uvx <path>]
  python guard.py stop
  python guard.py status
  python guard.py check-abort
  python guard.py touch
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

STATE_DIR = Path.home() / ".gemini" / "antigravity" / "plugin_data" / "computer-use"
PID_FILE = STATE_DIR / "guard.pid"
ABORT_FILE = STATE_DIR / "abort.flag"
STATE_FILE = STATE_DIR / "guard_state.json"
HEARTBEAT_FILE = STATE_DIR / "heartbeat.txt"
LOG_FILE = STATE_DIR / "guard.log"


def ensure_state_dir() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)


def write_heartbeat() -> None:
    ensure_state_dir()
    HEARTBEAT_FILE.write_text(f"{time.time():.6f}", encoding="utf-8")


def write_state(target: str, system: str, timeout: float) -> None:
    ensure_state_dir()
    STATE_FILE.write_text(
        json.dumps(
            {
                "target": target,
                "started_at": time.time(),
                "os": system,
                "timeout": timeout,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def is_pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if platform.system() == "Windows":
        import ctypes
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return False
        exit_code = ctypes.c_ulong()
        ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
        ctypes.windll.kernel32.CloseHandle(handle)
        return exit_code.value == 259  # STILL_ACTIVE
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _find_uv_binary(uvx_hint: str = "") -> str:
    """Find `uv` binary, preferring the sibling of `--uvx` if provided."""
    if uvx_hint:
        p = Path(uvx_hint)
        cand = p.parent / ("uv.exe" if platform.system() == "Windows" else "uv")
        if cand.is_file():
            return str(cand)
    found = shutil.which("uv")
    if found:
        return found
    for d in [
        Path.home() / ".local" / "bin",
        Path.home() / ".cargo" / "bin",
        Path("/opt/homebrew/bin"),
        Path("/usr/local/bin"),
    ]:
        cand = d / ("uv.exe" if platform.system() == "Windows" else "uv")
        if cand.is_file():
            return str(cand)
    return ""


def _can_import_mac_deps() -> bool:
    try:
        import AppKit  # noqa: F401
        import Quartz  # noqa: F401
        return True
    except Exception:
        return False


def cmd_start(target: str, timeout: float, uvx_hint: str) -> int:
    ensure_state_dir()
    if ABORT_FILE.exists():
        ABORT_FILE.unlink()

    system = platform.system()
    write_heartbeat()
    write_state(target, system, timeout)

    if PID_FILE.exists():
        try:
            old_pid = int(PID_FILE.read_text(encoding="utf-8").strip())
            if is_pid_alive(old_pid):
                print(f"Guard already running (pid={old_pid})")
                return 0
        except Exception:
            pass

    here = Path(__file__).resolve().parent
    if system == "Windows":
        worker = here / "guard_win.py"
        cmd = [
            sys.executable,
            str(worker),
            "--state-dir",
            str(STATE_DIR),
            "--target",
            target,
            "--timeout",
            str(timeout),
        ]
    elif system == "Darwin":
        worker = here / "guard_mac.py"
        worker_args = [
            str(worker),
            "--state-dir",
            str(STATE_DIR),
            "--target",
            target,
            "--timeout",
            str(timeout),
        ]
        if _can_import_mac_deps():
            cmd = [sys.executable, *worker_args]
        else:
            uv_bin = _find_uv_binary(uvx_hint)
            if uv_bin:
                cmd = [
                    uv_bin,
                    "run",
                    "--quiet",
                    "--with",
                    "pyobjc-framework-Cocoa",
                    "--with",
                    "pyobjc-framework-Quartz",
                    "python",
                    *worker_args,
                ]
            else:
                cmd = [sys.executable, *worker_args]
    else:
        print(f"Unsupported OS for guard: {system}", file=sys.stderr)
        return 1

    kwargs = {}
    if system == "Windows":
        DETACHED_PROCESS = 0x00000008
        CREATE_NEW_PROCESS_GROUP = 0x00000200
        kwargs["creationflags"] = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True

    with open(LOG_FILE, "a", encoding="utf-8") as log_f:
        log_f.write(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] Starting guard: {cmd}\n")
        log_f.flush()
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=log_f,
            **kwargs,
        )
    PID_FILE.write_text(str(proc.pid), encoding="utf-8")
    print(f"Guard started (pid={proc.pid}, os={system}, target={target!r}, timeout={timeout})")
    return 0


def cmd_stop() -> int:
    ensure_state_dir()
    if PID_FILE.exists():
        try:
            pid = int(PID_FILE.read_text(encoding="utf-8").strip())
            if is_pid_alive(pid):
                if platform.system() == "Windows":
                    subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
                else:
                    os.kill(pid, signal.SIGTERM)
        except Exception:
            pass
        PID_FILE.unlink(missing_ok=True)
    STATE_FILE.unlink(missing_ok=True)
    print("Guard stopped")
    return 0


def cmd_status() -> int:
    running = False
    pid = None
    if PID_FILE.exists():
        try:
            pid = int(PID_FILE.read_text(encoding="utf-8").strip())
            running = is_pid_alive(pid)
        except Exception:
            pass
    aborted = ABORT_FILE.exists()
    print(json.dumps({"running": running, "pid": pid, "aborted": aborted}))
    return 0


def cmd_check_abort() -> int:
    if ABORT_FILE.exists():
        print("ABORTED")
        return 2
    print("OK")
    return 0


def cmd_touch() -> int:
    write_heartbeat()
    print("OK")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="action", required=True)
    p_start = sub.add_parser("start")
    p_start.add_argument("--target", default="")
    p_start.add_argument("--timeout", type=float, default=20.0)
    p_start.add_argument("--uvx", default="")
    sub.add_parser("stop")
    sub.add_parser("status")
    sub.add_parser("check-abort")
    sub.add_parser("touch")
    args = parser.parse_args()

    if args.action == "start":
        return cmd_start(args.target, args.timeout, args.uvx)
    if args.action == "stop":
        return cmd_stop()
    if args.action == "status":
        return cmd_status()
    if args.action == "check-abort":
        return cmd_check_abort()
    if args.action == "touch":
        return cmd_touch()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
