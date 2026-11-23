#!/usr/bin/env bash
# Computer Use 插件一键安装（macOS / Linux, v0.2.4）
# 用法：bash install.sh
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="$SCRIPT_DIR/plugin"
DEST="$HOME/.gemini/config/plugins/computer-use"

# 清理残留旧守卫进程
if [ -f "$DEST/guard/guard.py" ]; then
  python3 "$DEST/guard/guard.py" stop >/dev/null 2>&1 || true
fi

echo "[1/4] 检查 Python 与 uv ..."
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"
PY="$(command -v python3 || command -v python || true)"
if [ -z "$PY" ]; then
  echo "未找到 Python 3，请先安装 Python 3。" >&2
  exit 1
fi
PY="$("$PY" -c 'import sys; print(sys.executable)')"
echo "    python: $PY"

if ! command -v uv >/dev/null 2>&1; then
  echo "未找到 uv，正在安装 ..."
  if command -v brew >/dev/null 2>&1; then brew install uv
  else curl -LsSf https://astral.sh/uv/install.sh | sh; fi
  export PATH="$HOME/.local/bin:$HOME/.cargo/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"
fi
UV="$(command -v uv)"
echo "    uv: $UV"

echo "[2/4] 复制插件到 $DEST ..."
mkdir -p "$DEST"
rm -f "$DEST/guard/mcp_proxy.py"
cp -R "$SRC/." "$DEST/"

echo "[3/4] 创建插件专属 .venv 并安装轻量依赖 ..."
VENV_DIR="$DEST/.venv"
VENV_PY="$VENV_DIR/bin/python"
SERVER_PY="$DEST/guard/server.py"
"$UV" venv "$VENV_DIR" --python "$PY" --clear
if [ "$(uname)" = "Darwin" ]; then
  "$UV" pip install --python "$VENV_PY" mss pillow pyobjc-framework-Cocoa pyobjc-framework-Quartz
else
  "$UV" pip install --python "$VENV_PY" mss pillow
fi

echo "[4/4] 写入直连配置并校验 ..."
"$VENV_PY" - "$DEST/mcp_config.json" "$VENV_PY" "$SERVER_PY" <<'EOF'
import json, sys
cfg_path, py_exe, server_py = sys.argv[1:4]
with open(cfg_path, encoding="utf-8") as f:
    c = json.load(f)
srv = c["mcpServers"]["computer-use-control"]
srv["command"] = py_exe
srv["args"] = [server_py if a == "__SERVER_PATH__" else a for a in srv["args"]]
with open(cfg_path, "w", encoding="utf-8") as f:
    json.dump(c, f, indent=2, ensure_ascii=False)
    f.write("\n")
EOF

"$VENV_PY" -c "import mss, PIL; print('原生后端依赖就绪')"
if [ "$(uname)" = "Darwin" ]; then
  "$VENV_PY" -c "import AppKit, Quartz; print('macOS Guard 依赖就绪')"
  echo
  echo "macOS 需要手动授权（无法脚本代劳）："
  echo "  系统设置 -> 隐私与安全性 -> 屏幕录制 / 辅助功能"
  echo "  为 Antigravity（以及你使用的终端）打开开关，然后重启 Antigravity。"
  open "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture" 2>/dev/null || true
  open "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility" 2>/dev/null || true
fi

echo
echo "安装完成（v0.2.3 丝滑单窗口微光版）。"
echo "重要提示：macOS 更新后请按 Command+Q 彻底退出 Antigravity 并重新打开（仅点关闭窗口不会重启后台插件进程）。"
