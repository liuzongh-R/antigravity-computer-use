#!/usr/bin/env bash
# Computer Use 插件一键安装（macOS / Linux, v0.1.1）
# 用法：bash install.sh
set -euo pipefail
SRC="$(cd "$(dirname "$0")" && pwd)/plugin"
DEST="$HOME/.gemini/config/plugins/computer-use"

echo "[1/5] 检查 Python 与 uv ..."
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

echo "[2/5] 复制插件到 $DEST ..."
mkdir -p "$DEST"
cp -R "$SRC/." "$DEST/"

echo "[3/5] 创建插件专属 .venv 并安装依赖 ..."
VENV_DIR="$DEST/.venv"
VENV_PY="$VENV_DIR/bin/python"
BACKEND_BIN="$VENV_DIR/bin/computer-control-mcp"
"$UV" venv "$VENV_DIR" --python "$PY" --clear
if [ "$(uname)" = "Darwin" ]; then
  "$UV" pip install --python "$VENV_PY" computer-control-mcp pyobjc-framework-Cocoa pyobjc-framework-Quartz
else
  "$UV" pip install --python "$VENV_PY" computer-control-mcp
fi

echo "[4/5] 写入直连代理配置 ..."
PROXY_PATH="$DEST/guard/mcp_proxy.py"
"$VENV_PY" - "$DEST/mcp_config.json" "$VENV_PY" "$PROXY_PATH" "$BACKEND_BIN" <<'EOF'
import json, sys
cfg_path, py_exe, proxy_path, backend_bin = sys.argv[1:5]
with open(cfg_path, encoding="utf-8") as f:
    c = json.load(f)
srv = c["mcpServers"]["computer-use-control"]
srv["command"] = py_exe
srv["args"] = [
    proxy_path if a == "__PROXY_PATH__" else (backend_bin if a == "__BACKEND_PATH__" else a)
    for a in srv["args"]
]
with open(cfg_path, "w", encoding="utf-8") as f:
    json.dump(c, f, indent=2, ensure_ascii=False)
    f.write("\n")
EOF

echo "[5/5] 预热 OCR 模型与权限检查 ..."
"$VENV_PY" -c "import computer_control_mcp; print('依赖与 OCR 模型就绪')"
if [ "$(uname)" = "Darwin" ]; then
  "$VENV_PY" -c "import AppKit, Quartz; print('mac guard deps ok')"
  echo
  echo "macOS 需要手动授权（无法脚本代劳）："
  echo "  系统设置 -> 隐私与安全性 -> 屏幕录制 / 辅助功能"
  echo "  为 Antigravity（以及你使用的终端）打开开关，然后重启 Antigravity。"
  open "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture" 2>/dev/null || true
  open "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility" 2>/dev/null || true
fi

echo
echo "安装完成（v0.1.1 直连模式）。请重启 Antigravity，或新开一个对话，然后说：'测试：打开 TextEdit 输入 Hello'。"
