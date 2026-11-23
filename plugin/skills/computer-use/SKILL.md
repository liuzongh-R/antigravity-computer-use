---
name: computer-use
description: 通过极速原生 computer-use-control MCP 工具直接操控用户桌面（截图、鼠标、键盘、窗口），支持 Windows 与 macOS。当用户要求点击桌面图标、操作本地 GUI 软件、或无法用命令行/浏览器完成的界面操作时使用。
---

# Computer Use 桌面控制（Windows / macOS · v0.2.1）

## 0. 先选对路线（越靠前越快）
1. **命令行**：开应用、读写文件、改配置优先用 `run_command`。
   - Windows：`Start-Process <app>`；macOS：`open -a "<App>"`。
2. **浏览器子智能体**：网页内的操作。
3. **桌面 MCP 工具**：只有必须点 GUI 时才用。

## 1. 极速操作与坐标规范（大幅减少往返轮次）
- **合并批处理，1~2 轮搞定**：把所有确定性连续步骤（例如 `activate_window` → `click` → `type` → `press`）**合并进单次 `execute_actions`**，并带上 **`release_after: true`**，执行完毕自动解锁，省掉多次大模型往返思考与额外的 `release_control` 调用！
- **无需动不动全屏截图**：如果只需要激活已有窗口并直接输入文字（如记事本/TextEdit），**直接调 `execute_actions([activate_window, type])`**，不用先截图；只有需要找按钮坐标时才先 `take_screenshot`。
- **截图像素即点击坐标**：`take_screenshot` 返回缩放后的 JPEG 图像（默认最大宽 1024px，更快传输；需看极小文字时可传 `max_width=1600`），所有鼠标工具（`click_screen`、`move_mouse`、`drag_mouse`、`scroll`）**直接传入你在截图上看到的像素坐标即可**，底层会自动精准换算为物理/虚拟桌面坐标，**无需手工换算缩放比例**。
- **`type_text` 原生支持中英文**：已使用底层 Unicode 注入，**完全无视系统输入法中英文状态**，也不会丢字，中英文长短文本都可直接调用 `type_text`。
- **优先键盘快捷键**：使用 `press_keys`（如 `ctrl+v`、`command+v`、`alt+tab`）减少鼠标寻找。

## 2. AI 守卫与锁定规则（自动提示 + 单窗口/全局锁定 + 立即解锁）
- **自动拉起守卫**：调用 `take_screenshot`、`activate_window` 或任意键鼠工具时，服务器会自动弹出 Codex 风格提示卡片与蓝色高亮边框（Windows 锁定全局除 `Esc` 外键鼠；macOS **必须先指定非空 `target`（即调用 `activate_window`）才会仅锁定该目标窗口**，且永远不锁鼠标移动、外部点击与 `Command+Tab`）。
- **必须及时解锁**：若未在最后一次 `execute_actions` 设置 `release_after: true`，**完成桌面操作后务必调用 `release_control`**，立刻归还控制权。
- **Esc 中止处理**：一旦任意工具返回 `ABORTED_BY_USER`（`isError: true`），说明用户已按 `Esc` 主动退出，**必须立即停止后续所有桌面操作**，并向用户汇报“已按 Esc 退出 AI 操作”。
- **典型极速循环**：能直接 `execute_actions(..., release_after=true)` 一步到位就一步到位；需要看屏找位置时：`take_screenshot` 观察 → `execute_actions(..., release_after=true)` 批量执行并自动解锁。

## 3. macOS 注意事项
- **权限**：系统设置 → 隐私与安全性 → **屏幕录制**、**辅助功能**，需为运行宿主（Antigravity、终端、`python`）授权，授权后需**重启宿主应用**。截图全黑或无反应，首先检查此项。
- 快捷键用 `command` 而非 `ctrl`（复制 `command+c`、粘贴 `command+v`、`command+space` 打开 Spotlight）。
- 提示与 `Esc` 仅在目标窗口处于前台时生效，用户切到其他软件不受影响；如弹出系统密码弹窗，调用 `release_control` 交还用户处理。

## 4. Windows 注意事项
- 以管理员权限运行的窗口，普通权限进程无法控制。
- `activate_window` 可直接使用窗口标题中的独特片段或正则（`use_regex=true`）。

## 5. 安全规则
- 删除文件、支付、发送消息/邮件、提交表单、修改系统设置、输入密码等不可逆或敏感操作，**执行前必须先征得用户确认**。
- 不处理验证码（CAPTCHA）或人机验证，遇到时调用 `release_control` 停止并告知用户。
