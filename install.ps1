# Computer Use 插件一键安装（Windows, v0.2.4）
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

$uv = (Get-Command uv -ErrorAction SilentlyContinue).Source
if (-not $uv) {
    $cands = @()
    $cands += (& $pyExe -c "import sysconfig;print(sysconfig.get_path('scripts','nt_user'))") + "\uv.exe"
    $cands += "$env:USERPROFILE\.local\bin\uv.exe"
    $uv = $cands | Where-Object { Test-Path $_ } | Select-Object -First 1
}
if (-not $uv) {
    Write-Host "未找到 uv，正在安装 ..."
    try {
        Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
    } catch {
        & $pyExe -m pip install --user uv
    }
    $cands = @(
        "$env:USERPROFILE\.local\bin\uv.exe",
        ((& $pyExe -c "import sysconfig;print(sysconfig.get_path('scripts','nt_user'))") + "\uv.exe")
    )
    $uv = $cands | Where-Object { Test-Path $_ } | Select-Object -First 1
}
if (-not $uv) { throw "安装 uv 后仍找不到 uv.exe" }
Write-Host "    uv: $uv"

Write-Host "[2/4] 复制插件到 $dest ..."
New-Item -ItemType Directory -Force $dest | Out-Null
# Clean stale scripts if upgrading from v0.1.x
Remove-Item "$dest\guard\mcp_proxy.py" -ErrorAction SilentlyContinue
Copy-Item "$src\*" $dest -Recurse -Force

Write-Host "[3/4] 准备插件专属 .venv 并安装轻量依赖 (mss, pillow) ..."
$venvDir = Join-Path $dest ".venv"
$venvPy = Join-Path $venvDir "Scripts\python.exe"
$serverPy = Join-Path $dest "guard\server.py"
$needVenv = $true
if (Test-Path $venvPy) {
    try {
        & $venvPy -c "import sys; print(sys.executable)" 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) { $needVenv = $false }
    } catch {}
}
if ($needVenv) {
    & $uv venv $venvDir --python $pyExe --clear
    if ($LASTEXITCODE -ne 0) { throw "创建 .venv 失败（如正在运行旧版 Antigravity，请先关闭后重试）" }
}
& $uv pip install --python $venvPy mss pillow
if ($LASTEXITCODE -ne 0) { throw "安装依赖 (mss, pillow) 失败" }

Write-Host "[4/4] 写入直连配置（无 BOM UTF-8）并校验 ..."
$cfgPath = Join-Path $dest "mcp_config.json"
$cfg = Get-Content $cfgPath -Raw -Encoding UTF8 | ConvertFrom-Json
$cfg.mcpServers.'computer-use-control'.command = $venvPy
$cfg.mcpServers.'computer-use-control'.args = @(
    $cfg.mcpServers.'computer-use-control'.args | ForEach-Object {
        if ($_ -eq "__SERVER_PATH__") { $serverPy } else { $_ }
    }
)
$json = $cfg | ConvertTo-Json -Depth 10
[System.IO.File]::WriteAllText($cfgPath, $json + "`n", [System.Text.UTF8Encoding]::new($false))
& $venvPy -c "import mss, PIL; print('原生后端依赖就绪')"
if ($LASTEXITCODE -ne 0) { throw "验证依赖导入失败" }

Write-Host ""
Write-Host "安装完成（v0.2.3 圆角微光极速版）。请重启 Antigravity，或新开一个对话测试桌面操控。"
