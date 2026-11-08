<#
GauForge WSL 服务启动器（Windows 端）

双击 start_gauforge.bat 即可；本脚本负责：
  1. 定位 WSL 发行版与部署目录（systemd_install.sh 所在目录）；
  2. 检查 WSL 是否启用 systemd；
  3. 交互级探活（Windows 侧 curl 经完整链路）：/system/health + 真实导入
     一个探活输入再删除（自清洁）——判据是 API 可用性而非 systemd 进程
     状态（unit 为 Type=simple，进程活着不代表服务可用）；
  4. 探活通过只提示不重启；失败自动修复：清崩溃循环（reset-failed + stop）
     → 运行 ./systemd_install.sh（幂等）→ 复验探活，仍失败给出排障指引。

首次运行会在 %LOCALAPPDATA%\GauForge\launcher.json 记住发行版与部署目录，
也可用参数覆盖：
  start_gauforge.bat -Distro Ubuntu -DeployPath /home/you/gauforge
#>
[CmdletBinding()]
param(
    [string]$DeployPath = "",
    [string]$Distro = ""
)

$ErrorActionPreference = 'Continue'

# WSL 的 stdout 是 UTF-8；统一控制台编码，避免中文日志乱码
try {
    $utf8 = New-Object System.Text.UTF8Encoding($false)
    [Console]::OutputEncoding = $utf8
    $OutputEncoding = $utf8
} catch {
    # 控制台不支持时忽略，不影响命令执行
}

$script:Distro = $Distro
$script:DeployPath = $DeployPath
$script:ExplicitDeploy = -not [string]::IsNullOrWhiteSpace($DeployPath)
$ScriptDir = $PSScriptRoot
$ConfigDir = Join-Path $env:LOCALAPPDATA 'GauForge'
$ConfigPath = Join-Path $ConfigDir 'launcher.json'

# Windows 10 1803+ 自带 curl.exe（注意不是 PS5.1 里指向 Invoke-WebRequest 的
# curl 别名）；探活全部走它，端到端覆盖 WSL2 localhost 转发
$script:HasCurl = [bool](Get-Command curl.exe -ErrorAction SilentlyContinue)

function Write-Info([string]$Message) {
    Write-Host $Message -ForegroundColor Cyan
}

function Write-Ok([string]$Message) {
    Write-Host $Message -ForegroundColor Green
}

function Write-Warn([string]$Message) {
    Write-Host $Message -ForegroundColor Yellow
}

function Write-Err([string]$Message) {
    Write-Host $Message -ForegroundColor Red
}

function Get-JournalHint {
    $base = 'journalctl --user -u gauforge.service -f'
    if ($script:Distro) {
        return "wsl -d `"$($script:Distro)`" -- $base"
    }
    return "wsl -- $base"
}

function Invoke-WslCapture {
    param([string[]]$WslArguments)

    $wslArgs = @()
    if ($script:Distro) {
        $wslArgs += @('-d', $script:Distro)
    }
    $wslArgs += $WslArguments

    $output = & wsl.exe @wslArgs 2>$null
    return [pscustomobject]@{
        Output   = @($output)
        ExitCode = $LASTEXITCODE
    }
}

function Invoke-Wsl {
    param([string[]]$WslArguments)

    $wslArgs = @()
    if ($script:Distro) {
        $wslArgs += @('-d', $script:Distro)
    }
    $wslArgs += $WslArguments

    & wsl.exe @wslArgs | Out-Host
    return $LASTEXITCODE
}

function Remove-TrailingSeparator {
    param([string]$Path)

    if ($Path -match '^[A-Za-z]:[\\/]$') {
        return $Path
    }
    while ($Path.Length -gt 1 -and ($Path.EndsWith('\') -or $Path.EndsWith('/'))) {
        $Path = $Path.Substring(0, $Path.Length - 1)
    }
    return $Path
}

# \\wsl.localhost\发行版\home\... 与 \\wsl$\发行版\home\... 归一成 /home/...
function Resolve-WslPath {
    param([string]$Path)

    if ($Path -match '^\\\\wsl(?:\.localhost|\$)\\([^\\]+)(?:\\(.*))?$') {
        $script:Distro = $Matches[1]
        if ($Matches[2]) {
            return '/' + ($Matches[2] -replace '\\', '/')
        }
        return '/'
    }
    return $Path
}

function Test-DeployPath {
    param([string]$Path)

    $result = Invoke-WslCapture @('--cd', $Path, '--exec', 'bash', '-lc', 'test -f systemd_install.sh')
    return ($result.ExitCode -eq 0)
}

# 部署包顶层同时有 systemd_install.sh 与 VERSION；源码仓库的 scripts/deploy
# 只有脚本、没有 VERSION，据此只认部署包，不会把开发端当服务装起来。
function Test-DeployPackage {
    param([string]$Path)

    $result = Invoke-WslCapture @('--cd', $Path, '--exec', 'bash', '-lc', 'test -f systemd_install.sh && test -f VERSION')
    return ($result.ExitCode -eq 0)
}

function Find-DeployCandidates {
    $findCommand = "find `$HOME -maxdepth 4 -type f -name systemd_install.sh 2>/dev/null"
    $result = Invoke-WslCapture @('-e', 'bash', '-lc', $findCommand)
    if ($result.ExitCode -ne 0) {
        return @()
    }

    $paths = @()
    foreach ($line in $result.Output) {
        $value = ([string]$line).Trim()
        if (-not $value.StartsWith('/')) {
            continue
        }
        $index = $value.LastIndexOf('/')
        if ($index -le 0) {
            continue
        }
        $dir = $value.Substring(0, $index)
        if ($paths -contains $dir) {
            continue
        }
        if (Test-DeployPackage $dir) {
            $paths += $dir
        }
    }
    return $paths
}

function Ask-DeployPath {
    if ([Console]::IsInputRedirected) {
        Write-Err '当前没有可交互的终端，无法询问部署目录。请用 -DeployPath 指定部署位置。'
        exit 1
    }
    $wslHome = ''
    $result = Invoke-WslCapture @('-e', 'printenv', 'HOME')
    if ($result.ExitCode -eq 0 -and $result.Output.Count -gt 0) {
        $wslHome = ([string]$result.Output[0]).Trim()
    }

    $defaultPath = if ($wslHome) { "$wslHome/gauforge" } else { '/home/<用户名>/gauforge' }
    while ($true) {
        Write-Host ''
        $answer = Read-Host "请输入 WSL 内的部署包目录（解压发布包后的顶层目录，例如 $defaultPath）"
        if ([string]::IsNullOrWhiteSpace($answer)) {
            $answer = $defaultPath
        }
        $answer = Remove-TrailingSeparator (Resolve-WslPath $answer.Trim())
        if (Test-DeployPackage $answer) {
            return $answer
        }
        if (Test-DeployPath $answer) {
            Write-Err "该目录是源码仓库的开发目录，不是部署包：$answer"
            Write-Host '启动器只运行部署包里的 systemd_install.sh，请解压发布包后重新指定。'
            continue
        }
        Write-Err "该目录下没有 systemd_install.sh：$answer"
    }
}

function Select-DeployCandidates {
    param([string[]]$Candidates)

    Write-Info '找到多个部署目录：'
    for ($i = 0; $i -lt $Candidates.Count; $i++) {
        Write-Host ("  [{0}] {1}" -f ($i + 1), $Candidates[$i])
    }
    $choice = Read-Host ("请输入序号（回车选择 1）")
    $index = 0
    if ($choice -match '^\d+$') {
        $number = [int]$choice
        if ($number -ge 1 -and $number -le $Candidates.Count) {
            $index = $number - 1
        }
    }
    return $Candidates[$index]
}

function Save-LauncherConfig {
    try {
        if (-not (Test-Path -LiteralPath $ConfigDir)) {
            New-Item -ItemType Directory -Force -Path $ConfigDir | Out-Null
        }
        $config = [ordered]@{
            distro = $script:Distro
            deploy = $script:DeployPath
        }
        $config | ConvertTo-Json | Set-Content -LiteralPath $ConfigPath -Encoding UTF8
    } catch {
        Write-Warn "配置未能保存：$($_.Exception.Message)"
    }
}

function Get-ListenPort {
    $port = 8300
    $command = ".venv/bin/python -c 'from web.src.main import resolved_listen_port; print(resolved_listen_port())'"
    $result = Invoke-WslCapture @('--cd', $script:DeployPath, '--exec', 'bash', '-lc', $command)
    if ($result.ExitCode -eq 0) {
        foreach ($line in $result.Output) {
            $value = ([string]$line).Trim()
            if ($value -match '^\d+$') {
                $port = [int]$value
                break
            }
        }
    }
    return $port
}

function Show-ServiceAddress {
    param([int]$Port)
    Write-Host ''
    Write-Ok '[完成] GauForge 已启动。'
    Write-Host "访问：http://127.0.0.1:$Port"
    Write-Host "日志：$(Get-JournalHint)"
}

function Show-WslDistros {
    $raw = (& wsl.exe -l -v 2>$null) -join "`n"
    $clean = ($raw -replace "`0", '').Trim()
    if ($clean) {
        Write-Host $clean
    }
}

# ---------------- 交互级探活（判据是 API 可用性，不是进程状态） ----------------

# 探活输入：极简可解析 g16 输入；可导入性由 web/tests/test_deploy_scripts.py
# 经真实 import_files 锁定。导入后即删，候选行与 inputs/ 副本均不留（自清洁）。
$script:ProbeGjf = @'
#p hf/sto-3g

gauforge launcher probe

0 1
H 0.0 0.0 0.0
H 0.0 0.0 0.74

'@

function Invoke-CurlCode {
    # curl 状态码经 -w %{http_code} 走 stdout；返回 ExitCode/Stdout
    param([string[]]$CurlArguments)

    $stdout = @(& curl.exe @CurlArguments 2>$null)
    $rc = $LASTEXITCODE
    if ($null -eq $rc) {
        $rc = -1
    }
    return [pscustomobject]@{
        ExitCode = $rc
        Stdout   = (@($stdout) -join '')
    }
}

function Test-HttpAlive {
    # L1：进程与 HTTP 栈可用性
    param([int]$Port)

    $url = "http://127.0.0.1:$Port/api/v1/system/health"
    if ($script:HasCurl) {
        $r = Invoke-CurlCode @('-s', '-o', 'NUL', '-w', '%{http_code}',
            '--connect-timeout', '2', '--max-time', '3', $url)
        return ($r.ExitCode -eq 0 -and $r.Stdout.Trim() -eq '200')
    }
    try {
        Invoke-WebRequest -UseBasicParsing -TimeoutSec 3 -Uri $url | Out-Null
        return $true
    } catch {
        return $false
    }
}

function Test-InteractiveAlive {
    # L2：真实 API 往返——导入探活输入（期望 201）后删除（期望 204）。
    # 返回 Ok / FailedAt（''|'import'|'delete'）/ Detail（降级或残留说明）。
    param([int]$Port)

    if (-not $script:HasCurl) {
        # 前 Win10 无内置 curl.exe，multipart 回退成本高：交互层降级跳过
        return [pscustomobject]@{ Ok = $true; FailedAt = '';
            Detail = 'curl.exe 缺失，交互层探活降级为仅健康检查' }
    }
    $prefix = 'gauforge-probe-' + [guid]::NewGuid().ToString('N')
    $probeFile = Join-Path $env:TEMP "$prefix.gjf"
    $bodyFile = Join-Path $env:TEMP "$prefix.json"
    try {
        [System.IO.File]::WriteAllText($probeFile, $script:ProbeGjf,
            (New-Object System.Text.UTF8Encoding($false)))
        $r = Invoke-CurlCode @('-s', '-o', $bodyFile, '-w', '%{http_code}',
            '--connect-timeout', '2', '--max-time', '10',
            '-F', "files=@$probeFile;filename=gauforge-probe.gjf",
            "http://127.0.0.1:$Port/api/v1/candidates")
        if ($r.ExitCode -ne 0 -or $r.Stdout.Trim() -ne '201') {
            return [pscustomobject]@{ Ok = $false; FailedAt = 'import';
                Detail = "导入探活输入未通过（exit=$($r.ExitCode) http=$($r.Stdout.Trim())）" }
        }
        $id = 0
        try {
            $resp = Get-Content -Raw -LiteralPath $bodyFile -Encoding UTF8 | ConvertFrom-Json
            $id = [int]$resp.files[0].id
        } catch {
            return [pscustomobject]@{ Ok = $false; FailedAt = 'import';
                Detail = "导入响应无法解析候选 id：$($_.Exception.Message)" }
        }
        if ($id -le 0) {
            return [pscustomobject]@{ Ok = $false; FailedAt = 'import';
                Detail = '导入响应未返回候选 id' }
        }
        $r = Invoke-CurlCode @('-s', '-o', 'NUL', '-w', '%{http_code}',
            '--connect-timeout', '2', '--max-time', '10', '-X', 'DELETE',
            "http://127.0.0.1:$Port/api/v1/candidates/$id")
        if ($r.ExitCode -ne 0 -or $r.Stdout.Trim() -ne '204') {
            return [pscustomobject]@{ Ok = $false; FailedAt = 'delete';
                Detail = "删除探活候选 $id 未通过（exit=$($r.ExitCode) http=$($r.Stdout.Trim())）；候选页可能出现可手动删除的 gauforge-probe.gjf" }
        }
        return [pscustomobject]@{ Ok = $true; FailedAt = ''; Detail = '' }
    } finally {
        Remove-Item -LiteralPath $probeFile -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $bodyFile -ErrorAction SilentlyContinue
    }
}

function Test-ServiceAlive {
    # 两层合流：返回 Alive / Reason（'health'|'import'|'delete'）/ Note
    param([int]$Port)

    if (-not (Test-HttpAlive -Port $Port)) {
        return [pscustomobject]@{ Alive = $false; Reason = 'health'; Note = '' }
    }
    $it = Test-InteractiveAlive -Port $Port
    if (-not $it.Ok) {
        return [pscustomobject]@{ Alive = $false; Reason = $it.FailedAt; Note = $it.Detail }
    }
    return [pscustomobject]@{ Alive = $true; Reason = ''; Note = $it.Detail }
}

# 读取上次保存的配置
if (Test-Path -LiteralPath $ConfigPath) {
    try {
        $saved = Get-Content -Raw -Encoding UTF8 -LiteralPath $ConfigPath | ConvertFrom-Json
        if (-not $script:Distro -and $saved.distro) {
            $script:Distro = [string]$saved.distro
        }
        if (-not $script:DeployPath -and $saved.deploy) {
            $script:DeployPath = [string]$saved.deploy
        }
    } catch {
        Write-Warn "配置读取失败，将重新探测：$($_.Exception.Message)"
    }
}

# 启动器与 systemd_install.sh 同目录时，直接使用所在目录
if (-not $script:DeployPath) {
    $sibling = Join-Path $ScriptDir 'systemd_install.sh'
    if (Test-Path -LiteralPath $sibling) {
        $script:DeployPath = $ScriptDir
    }
}

if ($script:DeployPath) {
    $script:DeployPath = Remove-TrailingSeparator (Resolve-WslPath $script:DeployPath)
}

# 未指定发行版时，记下默认发行版名称，便于提示命令
if (-not $script:Distro) {
    $probe = Invoke-WslCapture @('-e', 'printenv', 'WSL_DISTRO_NAME')
    if ($probe.ExitCode -eq 0 -and $probe.Output.Count -gt 0) {
        $script:Distro = ([string]$probe.Output[0]).Trim()
    }
}

$probe = Invoke-WslCapture @('-e', '/bin/true')
if ($probe.ExitCode -ne 0) {
    Write-Err '无法进入 WSL。请确认已安装 WSL2，并至少有一个可用的发行版。'
    Write-Host '当前发行版：'
    Show-WslDistros
    exit 1
}

# WSL2 未启用 systemd 时给出明确指引（先于目录询问，避免白问一轮）
$systemd = Invoke-WslCapture @('-e', 'bash', '-lc', 'test -d /run/systemd/system')
if ($systemd.ExitCode -ne 0) {
    Write-Err '当前 WSL 没有启用 systemd，无法安装/启动 gauforge.service。'
    Write-Host ''
    Write-Host '请在 WSL 中编辑 /etc/wsl.conf（没有就新建），加入：'
    Write-Host '    [boot]'
    Write-Host '    systemd=true'
    Write-Host '然后在 Windows 终端执行：'
    Write-Host '    wsl --shutdown'
    Write-Host '重新打开 WSL 后，再双击本脚本。'
    exit 1
}

# 显式指定的目录若是源码仓库，直接拒绝，避免把开发端装成服务
if ($script:ExplicitDeploy -and (Test-DeployPath $script:DeployPath) -and -not (Test-DeployPackage $script:DeployPath)) {
    Write-Err "这是源码仓库的开发目录，不是部署包：$($script:DeployPath)"
    Write-Host '启动器只运行部署包里的 systemd_install.sh，请解压发布包后重新指定。'
    exit 1
}

# 配置或参数中的目录失效时，重新探测，而不是直接报错退出
if ($script:DeployPath -and -not (Test-DeployPackage $script:DeployPath)) {
    Write-Warn "该目录不是部署包（缺少 VERSION）：$($script:DeployPath)"
    $script:DeployPath = ''
}

if (-not $script:DeployPath) {
    $candidates = @(Find-DeployCandidates)
    if ($candidates.Count -eq 1) {
        $script:DeployPath = $candidates[0]
    } elseif ($candidates.Count -gt 1) {
        $script:DeployPath = Select-DeployCandidates $candidates
    } else {
        Write-Info '未在 WSL 中自动发现部署包（顶层含 systemd_install.sh 与 VERSION）。'
        Write-Host '请先解压 gauforge-deploy 发布包，并在其中运行 ./install.sh。'
        $script:DeployPath = Ask-DeployPath
    }
    $script:DeployPath = Remove-TrailingSeparator $script:DeployPath
}

if (-not (Test-DeployPackage $script:DeployPath)) {
    Write-Err "该目录不是部署包：$($script:DeployPath)"
    Write-Host '部署包解压后顶层应同时包含 systemd_install.sh 与 VERSION。'
    exit 1
}

Save-LauncherConfig

$Port = Get-ListenPort

# 交互级探活门控：通过则不打扰（不重启健康实例），失败即修复
Write-Info '[探活] 检查服务交互可用性（/system/health + 导入/删除探活候选）…'
$alive = Test-ServiceAlive -Port $Port
if ($alive.Alive) {
    if ($alive.Note) {
        Write-Warn $alive.Note
    }
    Write-Ok 'GauForge 服务已在运行（交互自检通过），未重复执行安装脚本。'
    Show-ServiceAddress -Port $Port
    exit 0
}
if ($alive.Reason -eq 'health') {
    Write-Warn '服务未通过健康检查（进程已死或 WSL2 端口转发断链），进入修复流程。'
} else {
    Write-Warn "服务进程存活但 API 交互未通过（页面能打开不等于服务可用），进入修复流程。$($alive.Note)"
}

Write-Info '[修复] 清理崩溃循环状态并重装 systemd 服务 …'
# reset-failed + stop：把崩溃循环（activating/failed）清成干净停态，让
# systemd_install.sh 走全新安装分支（否则 enable --now 对循环中的 unit 可能空转）
$repairPreset = 'export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"; ' +
    'systemctl --user reset-failed gauforge.service 2>/dev/null; ' +
    'systemctl --user stop gauforge.service 2>/dev/null; exit 0'
$null = Invoke-WslCapture @('--cd', $script:DeployPath, '--exec', 'bash', '-lc', $repairPreset)

$rc = Invoke-Wsl @('--cd', $script:DeployPath, '--exec', 'bash', '-lc', './systemd_install.sh')
if ($null -eq $rc) {
    $rc = 1
}
if ($rc -ne 0) {
    Write-Host ''
    Write-Err "systemd_install.sh 退出码 $rc，服务未启动。"
    Write-Host "查看日志：$(Get-JournalHint)"
    exit $rc
}

Write-Info '[复验] 等待服务就绪（最长 15 秒）…'
$ready = $false
for ($i = 1; $i -le 15; $i++) {
    Start-Sleep -Seconds 1
    if ((Test-ServiceAlive -Port $Port).Alive) {
        $ready = $true
        break
    }
}
if (-not $ready) {
    Write-Host ''
    Write-Err '安装脚本已执行，但服务 15 秒内未通过交互级探活。'
    Write-Host '排障步骤：'
    $journalTail = 'journalctl --user -u gauforge.service -n 50 --no-pager'
    if ($script:Distro) {
        Write-Host "  1. 看日志：wsl -d `"$($script:Distro)`" -- $journalTail"
    } else {
        Write-Host "  1. 看日志：wsl -- $journalTail"
    }
    $innerUrl = "http://127.0.0.1:$Port/api/v1/system/health"
    if ($script:Distro) {
        Write-Host "  2. WSL 内自测（WSL 内 200 而 Windows 打不开 = localhost 转发断链）："
        Write-Host "     wsl -d `"$($script:Distro)`" -- curl -s -o /dev/null -w `"%{http_code}`" $innerUrl"
    }
    Write-Host '  3. 疑似转发断链：Windows 终端执行 wsl --shutdown，重开后再双击本脚本。'
    exit 1
}

Show-ServiceAddress -Port $Port
exit 0
