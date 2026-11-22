# Computer Use 插件一键安装（Windows, v0.1.1）
# 用法：右键 -> 使用 PowerShell 运行；或  powershell -ExecutionPolicy Bypass -File install.ps1
$ErrorActionPreference = "Stop"
$src = Join-Path $PSScriptRoot "plugin"
$dest = Join-Path $env:USERPROFILE ".gemini\config\plugins\computer-use"

Write-Host "[1/5] 检查 Python 与 uv ..."
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

Write-Host "[2/5] 复制插件到 $dest ..."
New-Item -ItemType Directory -Force $dest | Out-Null
Copy-Item "$src\*" $dest -Recurse -Force

Write-Host "[3/5] 创建插件专属 .venv 并安装 computer-control-mcp ..."
$venvDir = Join-Path $dest ".venv"
$venvPy = Join-Path $venvDir "Scripts\python.exe"
$backendExe = Join-Path $venvDir "Scripts\computer-control-mcp.exe"
& $uv venv $venvDir --python $pyExe --clear
if ($LASTEXITCODE -ne 0) { throw "创建 .venv 失败" }
& $uv pip install --python $venvPy computer-control-mcp
if ($LASTEXITCODE -ne 0) { throw "安装 computer-control-mcp 失败" }
if (-not (Test-Path $backendExe)) { throw "未找到后端可执行文件: $backendExe" }

Write-Host "[4/5] 写入直连配置（无 BOM UTF-8）..."
$cfgPath = Join-Path $dest "mcp_config.json"
$proxyPath = Join-Path $dest "guard\mcp_proxy.py"
$cfg = Get-Content $cfgPath -Raw -Encoding UTF8 | ConvertFrom-Json
$cfg.mcpServers.'computer-use-control'.command = $venvPy
$cfg.mcpServers.'computer-use-control'.args = @(
    $cfg.mcpServers.'computer-use-control'.args | ForEach-Object {
        if ($_ -eq "__PROXY_PATH__") { $proxyPath }
        elseif ($_ -eq "__BACKEND_PATH__") { $backendExe }
        else { $_ }
    }
)
$json = $cfg | ConvertTo-Json -Depth 10
[System.IO.File]::WriteAllText($cfgPath, $json + "`n", [System.Text.UTF8Encoding]::new($false))

Write-Host "[5/5] 预热 OCR 模型（首次约需几分钟）..."
& $venvPy -c "import computer_control_mcp; print('依赖与 OCR 模型就绪')"
if ($LASTEXITCODE -ne 0) { throw "预热导入 computer_control_mcp 失败" }

Write-Host ""
Write-Host "安装完成（v0.1.1 直连模式）。请重启 Antigravity，或新开一个对话，然后说：'测试：打开记事本输入 Hello'。"
