#!/usr/bin/env bash
# Computer Use 插件一键安装（macOS / Linux）
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

if ! command -v uvx >/dev/null 2>&1; then
  echo "未找到 uv，正在安装 ..."
  if command -v brew >/dev/null 2>&1; then brew install uv
  else curl -LsSf https://astral.sh/uv/install.sh | sh; fi
  export PATH="$HOME/.local/bin:$HOME/.cargo/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"
fi
UVX="$(command -v uvx)"
UV="$(command -v uv || echo "$(dirname "$UVX")/uv")"
echo "    uvx: $UVX"

echo "[2/5] 复制插件到 $DEST ..."
mkdir -p "$DEST"
cp -R "$SRC/." "$DEST/"

echo "[3/5] 写入 MCP 代理与绝对路径配置 ..."
PROXY_PATH="$DEST/guard/mcp_proxy.py"
"$PY" - "$DEST/mcp_config.json" "$PY" "$PROXY_PATH" "$UVX" <<'EOF'
import json, sys
cfg_path, py_exe, proxy_path, uvx_path = sys.argv[1:5]
with open(cfg_path, encoding="utf-8") as f:
    c = json.load(f)
srv = c["mcpServers"]["computer-use-control"]
srv["command"] = py_exe
srv["args"] = [
    proxy_path if a == "__PROXY_PATH__" else (uvx_path if a == "__UVX_PATH__" else a)
    for a in srv["args"]
]
with open(cfg_path, "w", encoding="utf-8") as f:
    json.dump(c, f, indent=2, ensure_ascii=False)
    f.write("\n")
EOF

echo "[4/5] 预下载依赖与 OCR 模型（首次约需几分钟）..."
"$UVX" --from "computer-control-mcp@latest" python -c "import computer_control_mcp; print('依赖就绪')"

echo "[5/5] macOS Guard 依赖与权限检查 ..."
if [ "$(uname)" = "Darwin" ]; then
  if [ -x "$UV" ]; then
    echo "    预缓存 pyobjc-framework-Cocoa / Quartz ..."
    "$UV" run --with pyobjc-framework-Cocoa --with pyobjc-framework-Quartz python -c "import AppKit, Quartz; print('mac guard deps ok')"
  fi
  echo "macOS 需要手动授权（无法脚本代劳）："
  echo "  系统设置 -> 隐私与安全性 -> 屏幕录制 / 辅助功能"
  echo "  为 Antigravity（以及你使用的终端）打开开关，然后重启 Antigravity。"
  open "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture" 2>/dev/null || true
  open "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility" 2>/dev/null || true
fi

echo
echo "安装完成。请重启 Antigravity，或新开一个对话，然后说：'测试：打开 TextEdit 输入 Hello'。"
