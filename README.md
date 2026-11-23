# Antigravity Computer Use

适用于 **Antigravity** 的极速跨平台桌面控制插件（Windows / macOS · `v0.2.3`）。内置自研单进程 MCP 服务器（仅需 `mss` 与 `pillow` 两个基础依赖）、1024px JPEG 内存截屏与自动坐标映射、批量执行自动解锁（`execute_actions(..., release_after=true)`），以及 **浅蓝半透明微光圆角 AI 守卫**（毛玻璃悬浮胶囊、适配 Win/Mac 窗口圆角的细微光边框、兼容远控软件的魔数签名拦截、按 `Esc` 立即终止与 `release_control` 秒解）。

---

## v0.2.3 核心特性

| 能力维度 | Windows 版 | macOS 版 |
| :--- | :--- | :--- |
| **启动与运行速度** | 自研纯标准库单进程 MCP 服务，仅依赖 `mss` + `pillow`，冷启动 `< 0.1s`；支持 `execute_actions` + `release_after` 单轮完成多步并秒解 | 同左（外加 `pyobjc`）；事件驱动前台检测 + 排除 `MouseMoved`/`MouseDragged`，拖动其他窗口丝滑零卡顿 |
| **截屏与坐标映射** | 内存直出 1024px 缩放 JPEG 图像（更快传图识图），截图像素坐标自动精准映射虚拟桌面，免算 DPI 缩放 | 同左，自动适配 Retina 屏幕逻辑坐标，截图像素直接点击 |
| **文字输入** | 原生 Unicode `SendInput`，中英文直接输入，完全无视系统输入法 | 原生 `CGEventKeyboardSetUnicodeString`，中英文直接输入 |
| **微光圆角操作提示** | 原生 Win32 Per-Pixel Alpha 分层窗口渲染：`2px` 浅蓝半透明微光圆角细边框 + 顶部深空磨砂胶囊（**本机与 GameViewer 等远控均清晰可见**） | 适配 macOS `11pt` 圆角的 `2pt` 浅蓝半透明微光细边框 + 原生 `NSVisualEffectView` 毛玻璃悬浮胶囊；**通过 `NSWindowAbove` 紧贴目标窗口正上方，即使被其他软件盖住一部分，后面露出的部分依然可见提示** |
| **精准输入锁定** | 独立纯 Win32 `GetMessageW` 钩子线程，**仅放行带专属魔数 `0x41475943` 的 AI 事件**，物理及远控键鼠全部禁止 | **基于唯一窗口 ID `(pid, window_id)` 严格单窗口锁定**：不随前台漂移、不锁鼠标移动/拖动；允许窗口外点击、`Command+Tab` 与 `Command+~`；仅当目标窗口激活在最前时锁定其内部输入 |
| **按 `Esc` 退出与解锁** | 全局按 `Esc` 毫秒级卸载钩子并中止 AI；`execute_actions` 设 `release_after=true` 或调用 `release_control` 秒解 | 仅在**点击并激活已绑定的目标窗口**后按 `Esc` 才终止 AI；在其他软件中完全正常使用 |

---

## 快速安装

### macOS 版安装（任选一种）

1. **一行命令远程安装（最省事，终端任意目录直接粘贴）**：
   ```bash
   curl -fsSL https://raw.githubusercontent.com/liuzongh-R/antigravity-computer-use/main/install-remote.sh | bash
   ```
2. **下载压缩包在终端安装**：从 Releases 下载 `antigravity-computer-use-macos.zip` 并解压后，先 `cd` 进解压目录再运行：
   ```bash
   cd ~/Downloads/antigravity-computer-use-macos && bash ./install.sh
   ```
3. **直接双击安装**：解压 `antigravity-computer-use-macos.zip` 后，双击其中的 `install.command`（如系统提示未验证开发者，右键 → 打开即可）。

**安装后必须开启系统权限**：
前往「系统设置 → 隐私与安全性」，为 **Antigravity**（及安装用的终端）打开：
- **屏幕录制（Screen Recording）**
- **辅助功能（Accessibility）**
授权完成后**彻底重启 Antigravity**。

### Windows 版安装

1. 从 Releases 下载 `antigravity-computer-use-windows.zip` 并解压（需已安装 Python 3）。
2. 进入解压目录 `antigravity-computer-use-windows`，运行：
   ```powershell
   powershell -ExecutionPolicy Bypass -File install.ps1
   ```
3. 脚本会自动安装 `uv`、建立插件专属 `.venv`（仅装 `mss` 与 `pillow`，数秒完成）并生成无 BOM UTF-8 的直连配置。
4. **重启 Antigravity 或新开一个对话**即可使用。

---

## 日常使用与测试示例

- `截一张屏幕截图，告诉我桌面上有哪些窗口`
- `测试：打开记事本（macOS：TextEdit）并输入 Hello 测试中文输入`
- `切换到微信窗口并查看最新消息`

AI 开始截屏或操控时会自动弹出提示卡片并锁定键鼠；操作完成后会自动调用 `release_control` 秒解。期间如需随时接管，按 `Esc`（macOS 需点击回到被操作窗口再按 `Esc`）即可立即退出。

---

## 目录结构

```text
antigravity-computer-use/
├── install.ps1                 # Windows 一键安装脚本
├── install.sh                  # macOS / Linux 一键安装脚本
├── install.command             # macOS 双击启动安装包装脚本
├── install-remote.sh           # macOS / Linux 一行远程安装脚本
├── LICENSE                     # MIT 开源协议
├── README.md                   # 项目说明文档
├── scripts/
│   └── build_releases.py       # 构建双端带顶层目录的发行压缩包（输出至 dist/）
└── plugin/                     # Antigravity 插件主体
    ├── plugin.json             # 插件元数据
    ├── mcp_config.json         # MCP 直连配置模板
    ├── guard/
    │   ├── server.py           # 极速单进程原生 MCP 服务器（12 个工具 + 自动坐标映射）
    │   ├── input_win.py        # Windows 原生 SendInput 与窗口控制（含魔数签名）
    │   ├── input_mac.py        # macOS 原生 Quartz / AppKit 控制（含魔数签名）
    │   ├── guard.py            # 跨平台守卫管理与 CLI
    │   ├── guard_win.py        # Windows 独立钩子线程、全拦截与 Codex 风格提示
    │   └── guard_mac.py        # macOS 目标窗口跟随提示、蓝框与 CGEventTap 拦截
    └── skills/
        └── computer-use/
            └── SKILL.md        # 智能体桌面操作规范
```

---

## 排错与日志路径

- **守卫运行日志**：`~/.gemini/antigravity/plugin_data/computer-use/guard.log`（Windows 正常启动后会记录 `hooks_installed kb=True ms=True`；macOS 会记录 `mac_event_tap_installed=True`）。
- **Mac 报 `No such file or directory`**：请使用上方方式 1 的一行 `curl | bash` 命令，或确保已 `cd` 进入解压后的 `antigravity-computer-use-macos` 目录再执行 `bash ./install.sh`。
- **Mac 截图黑屏 / 点击无反应 / `CGEventTapCreate` 失败**：请检查「系统设置 → 隐私与安全性」中的「屏幕录制」和「辅助功能」是否已勾选 Antigravity 与终端，勾选后必须重启 Antigravity。
- **Windows 无法控制管理员窗口**：以管理员身份运行的程序界面需同权限或手动处理。

---

## 开源协议

本项目采用 [MIT License](LICENSE) 开源。
