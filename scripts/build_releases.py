#!/usr/bin/env python3
"""Build separate Windows and macOS release archives in dist/."""
from __future__ import annotations

from pathlib import Path
import shutil
import zipfile

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
PLUGIN_DIR = ROOT / "plugin"

COMMON_DOCS = ["README.md", "LICENSE"]
EXEC_SUFFIXES = {".py", ".sh", ".command"}


def _is_ignored(path: Path) -> bool:
    parts = set(path.parts)
    if "__pycache__" in parts:
        return True
    if path.suffix in {".pyc", ".pyo", ".pyd"}:
        return True
    if path.name in {".DS_Store", "Thumbs.db"}:
        return True
    return False


def _add_file_to_zip(zf: zipfile.ZipFile, src: Path, arcname: str, mode: int = 0o644) -> None:
    data = src.read_bytes()
    if src.suffix in {".sh", ".command"}:
        data = data.replace(b"\r\n", b"\n")
    zi = zipfile.ZipInfo(arcname)
    zi.create_system = 3
    zi.compress_type = zipfile.ZIP_DEFLATED
    zi.external_attr = ((0o100000 | mode) & 0xFFFF) << 16
    zf.writestr(zi, data)


def build_zip(
    out_name: str,
    top_dir: str,
    root_scripts: list[str],
    excluded_files: set[str],
) -> Path:
    out_path = DIST / out_name
    with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for script_name in root_scripts:
            src = ROOT / script_name
            mode = 0o755 if src.suffix in {".sh", ".command"} else 0o644
            _add_file_to_zip(zf, src, f"{top_dir}/{script_name}", mode=mode)

        for doc in COMMON_DOCS:
            _add_file_to_zip(zf, ROOT / doc, f"{top_dir}/{doc}", mode=0o644)

        for file_path in sorted(PLUGIN_DIR.rglob("*")):
            if not file_path.is_file() or _is_ignored(file_path):
                continue
            if file_path.name in excluded_files:
                continue
            rel = file_path.relative_to(ROOT).as_posix()
            file_mode = 0o755 if file_path.suffix in EXEC_SUFFIXES else 0o644
            _add_file_to_zip(zf, file_path, f"{top_dir}/{rel}", mode=file_mode)

    return out_path


def main() -> int:
    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir(parents=True, exist_ok=True)

    win_zip = build_zip(
        "antigravity-computer-use-windows.zip",
        top_dir="antigravity-computer-use-windows",
        root_scripts=["install.ps1"],
        excluded_files={"guard_mac.py", "input_mac.py"},
    )
    mac_zip = build_zip(
        "antigravity-computer-use-macos.zip",
        top_dir="antigravity-computer-use-macos",
        root_scripts=["install.sh", "install.command"],
        excluded_files={"guard_win.py", "input_win.py"},
    )

    print(f"Built Windows release: {win_zip}")
    print(f"Built macOS release:   {mac_zip}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
