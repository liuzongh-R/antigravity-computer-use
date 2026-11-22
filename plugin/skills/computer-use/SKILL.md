---
name: computer-use
description: 通过 computer-use-control MCP 工具直接操控用户桌面（截图、OCR、鼠标、键盘、窗口），支持 Windows 与 macOS。当用户要求点击桌面图标、操作本地 GUI 软件、或无法用命令行/浏览器完成的界面操作时使用。
---

# Computer Use 桌面控制（Windows / macOS）

## 0. 先选对路线（越靠前越快）
1. **命令行**：开应用、读写文件、改配置优先用 `run_command`。
   - Windows：`Start-Process <app>`；macOS：`open -a "<App>"`。
2. **浏览器子智能体**：网页内的操作。
3. **桌面 MCP 工具**：只有必须点 GUI 时才用。

## 1. 提速策略
- **合并动作**：确定性的连续步骤（点击→等待→粘贴→回车）打包进一次 `execute_actions`，只在关键节点截图确认，不要每步都截图。
- **默认 `take_screenshot`**：多模态模型直接看图即可。仅在文字很小、需要精确坐标时才用 `take_screenshot_with_ocr`（本地 OCR 较慢）。
- **输入用剪贴板**：长文本/中文不要用 `type_text`（慢、丢字、被输入法干扰）。
  - Windows：`run_command` 执行 `Set-Clipboard -Value '文本'`，再 `press_keys` `ctrl+v`。
  - macOS：`printf '%s' '文本' | pbcopy`，再 `press_keys` `command+v`。
  - 仅短英文/数字可用 `type_text`（Windows 新版 WinUI 应用需 interval≈0.05）。
- **优先键盘快捷键**代替鼠标寻找按钮。
- 优先按窗口标题片段激活窗口，避免重复启动应用。

## 2. 操作循环与 AI 守卫（自动提示 + 锁定 + Esc 硬拦截）
- **守卫已由 MCP 代理自动管理**：发起点击/输入等桌面动作工具时，透明 MCP 代理会自动启动守卫（显示提示条与蓝色细边框、锁定用户输入，并在 20 秒无新动作后自动超时解锁），**无需手动调用 `guard.py`**。
- **Esc 中止处理**：一旦工具调用返回 `ABORTED_BY_USER`（`isError: true`），说明用户已按 `Esc` 主动退出，**必须立即停止所有后续桌面操作**，并向用户汇报“已按 Esc 退出 AI 操作”。
- **循环**：观察（截图/窗口列表）→ 先 `activate_window` 指定目标窗口（便于守卫准确锁定/展示目标名称）→ 一次动作或一批确定性动作 → 核对结果 → 继续。失败最多重试 2 次，然后向用户报告。

## 3. 坐标与缩放
- 先 `get_screen_size`，并与截图尺寸对比，计算缩放比例。
- **macOS Retina**：截图像素通常是逻辑坐标的 2 倍，点击坐标 = 截图像素 ÷ 缩放比例。
- **Windows**：125%/150% 缩放同理换算。
- 点击后若偏移，重新校准比例，不要靠猜。

## 4. Windows 已知坑
- 工具为懒加载时，先读 `<appDataDir>\mcp\computer-use_computer-use-control\<tool>.json` 再用 `call_mcp_tool` 调用（已配置核心工具预加载，通常可直接调用）。
- **中文输入法**会把英文字母转成中文，输入前按 `shift` 切到英文，或改用剪贴板粘贴。
- `activate_window` 报 `refused focus` 时，先 `click_screen` 点目标窗口再激活。
- 窗口模糊匹配不稳，使用标题中的独特片段或正则。
- 刚启动的应用可能暂时不在窗口列表，稍等或直接截图确认。
- 以管理员身份运行的窗口，普通权限进程无法控制。

## 5. macOS 注意事项
- **权限**：系统设置 → 隐私与安全性 → **屏幕录制**、**辅助功能**，需为运行宿主（Antigravity、终端、`uv`/`python`）授权，授权后需**重启宿主应用**。截图全黑或点击无反应，首先检查此项。
- 快捷键用 `command` 而非 `ctrl`（复制 `command+c`、粘贴 `command+v`、切应用 `command+tab`）。
- **Spotlight**：`command+space` 输入应用名回车，可快速启动；但更推荐 `open -a`。
- 激活应用：`osascript -e 'tell application "<App>" to activate'` 比 `activate_window` 更稳。
- 菜单栏操作可用 `osascript` / System Events 点击菜单项，比鼠标寻找更快更准。
- 全屏应用和多桌面（Spaces）下，窗口可能不在当前桌面，需先切换。
- 输入法同样可能干扰 `type_text`，优先剪贴板粘贴。
- 与 Windows 不同，macOS 上弹出系统权限/密码弹窗时，不要代替用户输入密码，交还用户处理。

## 6. 安全规则
- 删除文件、支付、发送消息/邮件、提交表单、修改系统设置、输入密码等不可逆或敏感操作，**执行前必须先征得用户确认**。
- 不处理验证码（CAPTCHA）或人机验证，遇到时停止并告知用户。
- 提醒用户在智能体操作期间尽量不要操作；如需随时接管，按 `Esc`（macOS 需先点击回到被操作的窗口再按 `Esc`）。
