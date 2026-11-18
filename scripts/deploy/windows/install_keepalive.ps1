<#
GauForge WSL KeepAlive 计划任务安装器（Windows 端）

作用：注册登录触发计划任务「GauForge WSL KeepAlive」——后台执行
  wsl.exe -d <发行版> -u root --exec /usr/bin/sleep infinity
恒持一个 WSL 会话引用，使 distro 永不满足空闲判定自动关机（WSL 只认
wsl.exe 会话引用、systemd 服务在跑不算存活依据——层 1 修复）；登录即
拉起 distro（免终端首启）。服务常驻另半边 = linger（systemd_install.sh
负责），两层缺一不可。

用法（PowerShell）：
  powershell -ExecutionPolicy Bypass -File install_keepalive.ps1 [-Distro <名称>] [-Elevated] [-Remove]
  -Distro    WSL 发行版名；缺省复用启动器口径：读 %LOCALAPPDATA%\GauForge\launcher.json
             （start_gauforge.ps1 记忆值），再探测第一个 Running/首个可用发行版
  -Elevated  管理员窗口注册 S4U 免密任务（注销后续跑）；缺省 Interactive——
             普通权限即可注册（部署机实测 S4U 注册需提权、Interactive 成功），
             AtLogOn 触发语义下注销即停、下次登录自动拉起，承诺域内无缺口
  -Remove    卸载本任务（只删本任务，不动其他）

设计要点：
  - 注册一律走 Principal 参数集（New-ScheduledTaskPrincipal + Register-ScheduledTask
    -Principal，全版本可用）：部署机实测（Win10 19045.6466 / PS5.1）
    Register-ScheduledTask 无 -LogonType 参数，直接传参路径不可用
  - ExecutionTimeLimit=PT0S 必设：schtasks 默认 72h 时限会杀 sleep infinity
  - 幂等：Register-ScheduledTask -Force 覆盖同名既有任务（改参数不重复建号）
  - wsl --shutdown 会杀 sleep 进程（任务注册仍在、State=Ready）：重跑本
    脚本或双击 start_gauforge.bat（启动器自愈复跑）即恢复
  - 手动兜底（极端环境 Register-ScheduledTask 不可用）：schtasks /create /xml
    按本脚本等价定义注册（任务 XML 须 UTF-16LE BOM；Export-ScheduledTask
    可导出已注册任务作模板）
#>
[CmdletBinding()]
param(
    [string]$Distro = "",
    [switch]$Elevated,
    [switch]$Remove
)

$ErrorActionPreference = 'Stop'
$TaskName = 'GauForge WSL KeepAlive'

function Write-Info([string]$Message) { Write-Host $Message -ForegroundColor Cyan }
function Write-Ok([string]$Message) { Write-Host $Message -ForegroundColor Green }
function Write-Warn([string]$Message) { Write-Host $Message -ForegroundColor Yellow }
function Write-Err([string]$Message) { Write-Host $Message -ForegroundColor Red }

# 发行版缺省探测（与 start_gauforge.ps1 同口径）：launcher.json 记忆值优先
function Get-DistroFromLauncherConfig {
    $configPath = Join-Path $env:LOCALAPPDATA 'GauForge\launcher.json'
    if (Test-Path -LiteralPath $configPath) {
        try {
            $config = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
            if ($config.distro) { return [string]$config.distro }
        } catch {
            Write-Warn "[keepalive] launcher.json 读取失败：$($_.Exception.Message)"
        }
    }
    return ''
}

function Get-DefaultDistro {
    try {
        $raw = (& wsl.exe -l -v 2>$null) -join "`n"
        $clean = ($raw -replace "`0", '').Trim()
        $lines = $clean -split "`r?`n" | Where-Object { $_.Trim() -ne '' } | Select-Object -Skip 1
        foreach ($line in $lines) {   # 优先 Running（最小扰动：不新拉 distro）
            $parts = ($line -split '\s+') | Where-Object { $_ -ne '' }
            if ($parts.Count -ge 3 -and $parts[1] -eq 'Running') { return $parts[0] }
        }
        foreach ($line in $lines) {
            $parts = ($line -split '\s+') | Where-Object { $_ -ne '' }
            if ($parts.Count -ge 3 -and $parts[0] -ne 'NAME') { return $parts[0] }
        }
    } catch {
        Write-Warn "[keepalive] wsl -l -v 探测失败：$($_.Exception.Message)"
    }
    return ''
}

if ($Remove) {
    if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Ok "[keepalive] 已卸载计划任务：$TaskName"
    } else {
        Write-Warn "[keepalive] 未发现计划任务：$TaskName（无需卸载）"
    }
    exit 0
}

# 发行版解析：参数 > launcher.json > 探测
if ([string]::IsNullOrWhiteSpace($Distro)) { $Distro = Get-DistroFromLauncherConfig }
if ([string]::IsNullOrWhiteSpace($Distro)) { $Distro = Get-DefaultDistro }
if ([string]::IsNullOrWhiteSpace($Distro)) {
    Write-Err '[keepalive] 未定位到 WSL 发行版：请用 -Distro 显式指定。'
    exit 1
}

# 提权检测：-Elevated 需管理员窗口；普通权限降级 Interactive（不静默）
$logonType = 'Interactive'
if ($Elevated) {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    $isAdmin = $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    if ($isAdmin) {
        $logonType = 'S4U'
    } else {
        Write-Warn '[keepalive] -Elevated 需管理员窗口；当前为普通权限，降级 Interactive（AtLogOn 语义下注销即停、下次登录自动拉起）。'
    }
}
$userId = "$env:USERDOMAIN\$env:USERNAME"

$action = New-ScheduledTaskAction -Execute 'wsl.exe' `
    -Argument "-d `"$Distro`" -u root --exec /usr/bin/sleep infinity"
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $userId
# ExecutionTimeLimit=([TimeSpan]::Zero) 即 PT0S：防 schtasks 默认 72h 时限杀任务
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -Hidden
$principalDef = New-ScheduledTaskPrincipal -UserId $userId -LogonType $logonType -RunLevel Limited

# 幂等注册：-Force 覆盖同名既有任务（改参数不重复建号）
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings -Principal $principalDef -Force | Out-Null

Start-ScheduledTask -TaskName $TaskName   # 注册当次立即生效
Start-Sleep -Seconds 1
$state = (Get-ScheduledTask -TaskName $TaskName).State
Write-Ok "[keepalive] 已注册并启动计划任务：$TaskName（LogonType=$logonType, Distro=$Distro, State=$state）"
Write-Info '[keepalive] distro 恒持一个 sleep 会话引用，不再因空闲自动关机；wsl --shutdown 后恢复口径见 deployment.md。'
