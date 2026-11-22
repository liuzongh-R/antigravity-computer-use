# Computer Use 插件一键安装（Windows）
# 用法：右键 -> 使用 PowerShell 运行；或  powershell -ExecutionPolicy Bypass -File install.ps1
$ErrorActionPreference = "Stop"
$src = Join-Path $PSScriptRoot "plugin"
$dest = Join-Path $env:USERPROFILE ".gemini\config\plugins\computer-use"

Write-Host "[1/4] 检查 Python 与 uv ..."
$pyExe = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $pyExe -and (Get-Command py -ErrorAction SilentlyContinue)) {
    $pyExe = (& py -3 -c "import sys; print(sys.executable)" 2>$null)
}
if (-not $pyExe) { throw "未找到 Python 3，请先安装 Python 3。" }
$pyExe = (& $pyExe -c "import sys; print(sys.executable)").Trim()
Write-Host "    python: $pyExe"

$uvx = (Get-Command uvx -ErrorAction SilentlyContinue).Source
if (-not $uvx) {
    $cands = @()
    $cands += (& $pyExe -c "import sysconfig;print(sysconfig.get_path('scripts','nt_user'))") + "\uvx.exe"
    $cands += "$env:USERPROFILE\.local\bin\uvx.exe"
    $uvx = $cands | Where-Object { Test-Path $_ } | Select-Object -First 1
}
if (-not $uvx) {
    Write-Host "未找到 uv，正在安装 ..."
    try {
        Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
    } catch {
        & $pyExe -m pip install --user uv
    }
    $cands = @(
        "$env:USERPROFILE\.local\bin\uvx.exe",
        ((& $pyExe -c "import sysconfig;print(sysconfig.get_path('scripts','nt_user'))") + "\uvx.exe")
    )
    $uvx = $cands | Where-Object { Test-Path $_ } | Select-Object -First 1
}
if (-not $uvx) { throw "安装 uv 后仍找不到 uvx.exe" }
Write-Host "    uvx: $uvx"

Write-Host "[2/4] 复制插件到 $dest ..."
New-Item -ItemType Directory -Force $dest | Out-Null
Copy-Item "$src\*" $dest -Recurse -Force

Write-Host "[3/4] 写入 MCP 代理与路径配置（无 BOM UTF-8）..."
$cfgPath = Join-Path $dest "mcp_config.json"
$proxyPath = Join-Path $dest "guard\mcp_proxy.py"
$cfg = Get-Content $cfgPath -Raw -Encoding UTF8 | ConvertFrom-Json
$cfg.mcpServers.'computer-use-control'.command = $pyExe
$cfg.mcpServers.'computer-use-control'.args = @(
    $cfg.mcpServers.'computer-use-control'.args | ForEach-Object {
        if ($_ -eq "__PROXY_PATH__") { $proxyPath }
        elseif ($_ -eq "__UVX_PATH__") { $uvx }
        else { $_ }
    }
)
$json = $cfg | ConvertTo-Json -Depth 10
[System.IO.File]::WriteAllText($cfgPath, $json + "`n", [System.Text.UTF8Encoding]::new($false))

Write-Host "[4/4] 预下载依赖与 OCR 模型（首次约需几分钟）..."
& $uvx --from "computer-control-mcp@latest" python -c "import computer_control_mcp; print('依赖就绪')"

Write-Host ""
Write-Host "安装完成。请重启 Antigravity，或新开一个对话，然后说：'测试：打开记事本输入 Hello'。"
