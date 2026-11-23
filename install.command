#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
bash ./install.sh
echo
read -r -p "安装已结束，按回车键关闭窗口..."
