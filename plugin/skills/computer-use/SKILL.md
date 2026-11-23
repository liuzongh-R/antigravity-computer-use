---
name: computer-use
description: 通过极速原生 computer-use-control MCP 工具直接操控用户桌面（截图、鼠标、键盘、窗口），支持 Windows 与 macOS。当用户要求点击桌面图标、操作本地 GUI 软件、或无法用命令行/浏览器完成的界面操作时使用。
---

# Computer Use 桌面控制（Windows / macOS · v0.2.0）

## 0. 先选对路线（越靠前越快）
1. **命令行**：开应用、读写文件、改配置优先用 `run_command`。
   - Windows：`Start-Process <app>`；macOS：`open -a "<App>"`。
2. **浏览器子智能体**：网页内的操作。
3. **桌面 MCP 工具**：只有必须点 GUI 时才用。

## 1. 极速操作与坐标规范
- **截图像素即点击坐标**：`take_screenshot` 返回缩放后的 JPEG 图像（默认最大宽 1280px），所有鼠标工具（`click_screen`、`move_mouse`、`drag_mouse`、`scroll`）**直接传入你在截图上看到的像素坐标即可**，底层会自动精准换算为物理/虚拟桌面坐标，**无需手工换算缩放比例**。
- **`type_text` 原生支持中英文**：已使用底层 Unicode 注入，**完全无视系统输入法中英文状态**，也不会丢字，中英文长短文本都可直接调用 `type_text`。
- **合并动作**：确定性的连续步骤（点击→等待→输入→回车）尽量打包进一次 `execute_actions`，只在关键节点截图核对。
- **优先键盘快捷键**：使用 `press_keys`（如 `ctrl+v`、`command+v`、`alt+tab`）减少鼠标寻找。

## 2. AI 守卫与锁定规则（自动提示 + 全拦截 + 立即解锁）
- **自动拉起守卫**：调用 `take_screenshot`、`activate_window` 或任意键鼠工具时，服务器会自动弹出 Codex 风格顶部提示卡片与蓝色高亮边框，并锁定用户除 `Esc` 外的一切物理及远控键鼠输入（若超过 45 秒无新操作会自动解锁）。
- **必须及时解锁**：**完成全部桌面操作并验证结果后，务必调用 `release_control`**，立刻关闭提示卡片和蓝框并归还键鼠控制权，不要让用户干等 45 秒！
- **Esc 中止处理**：一旦任意工具返回 `ABORTED_BY_USER`（`isError: true`），说明用户已按 `Esc` 主动退出，**必须立即停止后续所有桌面操作**，并向用户汇报“已按 Esc 退出 AI 操作”。
- **操作循环**：`activate_window` 指定目标窗口（如需要） → `take_screenshot` 观察 → `execute_actions` 或单步动作 → `take_screenshot` 核对 → **`release_control` 解锁**。

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
