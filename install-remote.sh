#!/usr/bin/env bash
# 一键远程安装 Antigravity Computer Use（macOS / Linux）
# 用法：curl -fsSL https://raw.githubusercontent.com/liuzongh-R/antigravity-computer-use/main/install-remote.sh | bash
set -euo pipefail

TAR_URL="https://github.com/liuzongh-R/antigravity-computer-use/archive/refs/heads/main.tar.gz"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

echo "正在下载最新版本..."
curl -fsSL "$TAR_URL" | tar -xz -C "$TMP_DIR"
bash "$TMP_DIR/antigravity-computer-use-main/install.sh"
