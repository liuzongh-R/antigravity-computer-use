# Antigravity Computer Use

适用于 **Antigravity** 的跨平台桌面控制插件（Windows / macOS），提供视觉截屏、OCR 识别、鼠标点击与拖拽、键盘输入、窗口切换等能力，并内置 **透明 MCP 代理 + AI 操作守卫**（操作提示条、蓝色细边框高亮、用户输入拦截、按 `Esc` 立即终止与超时自动解锁）。

---

## 核心特性对比（Windows vs macOS）

| 能力维度 | Windows 版 | macOS 版 |
| :--- | :--- | :--- |
| **视觉与控制后端** | `computer-control-mcp`（支持 WGC 窗口截图、RapidOCR、键鼠与窗口管理） | `computer-control-mcp`（截图、RapidOCR、键鼠与窗口管理） |
| **操作时视觉提示** | 屏幕顶部置顶半透明提示条 + 屏幕四边 4px 蓝色细边框（鼠标穿透） | **仅在被操作的目标窗口内部**显示提示条与四边 4px 蓝色细边框；切到其他应用自动隐藏 |
| **用户输入拦截** | 底层键鼠钩子（`WH_KEYBOARD_LL` / `WH_MOUSE_LL`）仅放行 AI 注入事件 | `CGEventTap` 拦截目标窗口内的物理键鼠输入；切换至其他应用时正常使用不拦截 |
| **按 `Esc` 退出方式** | 全局按 `Esc` 立即写入中止标志并退出锁定 | 只有**点击并激活目标窗口**后按 `Esc` 才终止 AI 操作；在其他软件中按 `Esc` 不误触 |
| **自动化兜底** | 20 秒无新动作心跳看门狗自动解除锁定 | 20 秒无新动作心跳看门狗自动解除锁定 |
| **安装与依赖** | 一键脚本自动配置 Python + `uv` 并预下载模型 | 一键脚本自动配置 Python + `uv` 并预缓存 `pyobjc` 与模型 |

---

## 工作原理

本插件通过一层轻量级的标准库 stdio MCP 代理（`mcp_proxy.py`）连接 Antigravity 与底层 `computer-control-mcp`：

1. **工具调用自动拉起守卫**：当智能体调用 `click_screen`、`type_text`、`press_keys`、`execute_actions`、`activate_window` 等动作工具时，代理会自动拉起对应系统的守卫进程（`guard_win.py` / `guard_mac.py`）并持续写入 `heartbeat.txt` 心跳；截屏、列窗口等只读工具也会在守卫运行期间刷新心跳，防止智能体识图思考时误超时。
2. **输入隔离与提示**：守卫启动后在屏幕或目标窗口上渲染穿透式提示条与细边框，同时拦截物理键鼠输入，确保人工操作不会与 AI 动作冲突。
3. **Esc 硬拦截与瞬时退出**：用户按下 `Esc` 后，守卫立即写下 `abort.flag` 并解除全部键鼠锁定；代理在收到后续任何动作或工具调用时直接拦截，返回 `ABORTED_BY_USER`（带 5 秒冷却期），无需消耗额外模型轮次即可中止任务。
4. **看门狗超时自动解锁**：若超过 20 秒没有任何桌面工具心跳，守卫看门狗会自动退出并释放所有系统钩子，避免网络异常或任务中断导致键鼠长期锁定。

---

## 快速安装

你可以从 GitHub Releases 下载对应平台的独立压缩包（`antigravity-computer-use-windows.zip` 或 `antigravity-computer-use-macos.zip`），或直接克隆本仓库后安装。

### Windows 版安装

1. 解压 `antigravity-computer-use-windows.zip`（需本机已安装 Python 3）。
2. 在解压目录中打开终端（PowerShell），运行：
   ```powershell
   powershell -ExecutionPolicy Bypass -File install.ps1
   ```
3. 脚本会自动完成：`uv` 检查与安装 → 复制插件至 `%USERPROFILE%\.gemini\config\plugins\computer-use` → 生成无 BOM UTF-8 的 `mcp_config.json` → 预下载 `computer-control-mcp` 与 OCR 模型。
4. **重启 Antigravity 或新开一个对话**使插件生效。

### macOS 版安装

1. 解压 `antigravity-computer-use-macos.zip`（需本机已安装 Python 3）。
2. 在终端进入解压目录并运行：
   ```bash
   bash install.sh
   ```
3. 脚本会自动完成：`uv` 检查与安装 → 复制插件至 `~/.gemini/config/plugins/computer-use` → 写入代理绝对路径 → 预下载 `computer-control-mcp` 与 OCR 模型 → 通过 `uv` 预缓存 `pyobjc-framework-Cocoa` 与 `pyobjc-framework-Quartz`。
4. **手动授予系统权限（必须）**：
   打开「系统设置 → 隐私与安全性」，分别为 **Antigravity**（以及运行脚本使用的终端）开启以下两项权限：
   - **屏幕录制（Screen Recording）**
   - **辅助功能（Accessibility）**
5. 授权完成后**彻底重启 Antigravity**。

---

## 日常使用与测试示例

安装完成后，在新对话中直接给出桌面操作指令即可，例如：

- `截一张屏幕截图，告诉我当前桌面上有哪些窗口`
- `测试：打开记事本（macOS：TextEdit）并输入 Hello from Antigravity`
- `切换到微信窗口并查看最新消息列表`

> **提示**：为了提升速度与准确率，内置技能规则 [SKILL.md](plugin/skills/computer-use/SKILL.md) 引导智能体优先使用命令行与剪贴板粘贴（`Ctrl+V` / `Command+V`），将连续确定性动作合并为一次 `execute_actions`，仅在必要时运行本地 OCR。

---

## 安全与 Esc 退出机制

- **高危操作确认**：涉及删除文件、支付、发送消息/邮件、提交表单、修改系统设置或输入密码时，智能体会先向用户确认；遇到验证码（CAPTCHA）会自动停止。
- **随时接管**：
  - **Windows**：AI 操作期间屏幕四边会出现蓝色高亮边框与顶部提示条，按 `Esc` 即可立即中止 AI 动作并恢复人工控制。
  - **macOS**：提示条与蓝色边框仅跟随被操作的目标窗口；AI 操作该窗口期间你仍可切换到其他应用正常工作；如需中止 AI，先点击回到被操作的窗口使其处于前台，再按 `Esc`。
- **自动兜底**：任何情况下只要超过 20 秒无新操作心跳，守卫均会自动退出。

---

## 目录结构

```text
antigravity-computer-use/
├── install.ps1                 # Windows 一键安装脚本
├── install.sh                  # macOS / Linux 一键安装脚本
├── LICENSE                     # MIT 开源协议
├── README.md                   # 项目说明文档
├── scripts/
│   └── build_releases.py       # 构建双端独立发行压缩包（输出至 dist/）
└── plugin/                     # Antigravity 插件主体
    ├── plugin.json             # 插件元数据
    ├── mcp_config.json         # MCP 服务器与预加载工具模板
    ├── guard/
    │   ├── mcp_proxy.py        # 透明 stdio MCP 代理（自动启停守卫与 Esc 硬拦截）
    │   ├── guard.py            # 跨平台守卫管理入口与状态检查
    │   ├── guard_win.py        # Windows 端提示条、蓝框与底层键鼠钩子
    │   └── guard_mac.py        # macOS 端目标窗口跟随提示、蓝框与 CGEventTap 拦截
    └── skills/
        └── computer-use/
            └── SKILL.md        # 智能体桌面操作与提速规范
```

---

## 排错与日志路径

- **守卫运行日志**：`~/.gemini/antigravity/plugin_data/computer-use/guard.log`
- **Mac 截图黑屏 / 点击无反应 / `CGEventTapCreate` 失败**：请检查「系统设置 → 隐私与安全性」中的「屏幕录制」和「辅助功能」是否已勾选 Antigravity 与终端，勾选后必须重启 Antigravity。
- **点击位置偏移**：通常由屏幕缩放（Windows 125%/150% 或 macOS Retina 2x）引起，可提示智能体先调用 `get_screen_size` 并对比截图分辨率进行校准。
- **工具未加载**：请确认插件目录位于 `~/.gemini/config/plugins/computer-use`，并新开对话或重启 Antigravity。

---

## 致谢与开源协议

- 底层桌面控制与 OCR 能力基于开源项目 [AB498/computer-control-mcp](https://github.com/AB498/computer-control-mcp)。
- 本项目采用 [MIT License](LICENSE) 开源。
