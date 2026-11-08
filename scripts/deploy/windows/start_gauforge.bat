@echo off
rem Double-click launcher for start_gauforge.ps1.
rem The script is looked up next to this file first, then under %LOCALAPPDATA%\GauForge
rem (the desktop shortcut uses the installed copy).
rem Default behavior: probe the service with a real API round-trip (health +
rem import/delete of a self-cleaning probe candidate); on failure it repairs
rem automatically (reset crash loop, run systemd_install.sh, re-verify).
rem Pass PowerShell parameters through, e.g.:
rem   start_gauforge.bat -Distro Ubuntu -DeployPath /home/you/gauforge
setlocal
chcp 65001 >nul

set "LAUNCHER=%~dp0start_gauforge.ps1"
if not exist "%LAUNCHER%" set "LAUNCHER=%LOCALAPPDATA%\GauForge\start_gauforge.ps1"
if not exist "%LAUNCHER%" (
    echo.
    echo [error] start_gauforge.ps1 not found.
    echo Put it next to this file, or under %%LOCALAPPDATA%%\GauForge.
    echo.
    if not defined GAUFORGE_NO_PAUSE pause
    exit /b 1
)

set "PS=powershell.exe"
where pwsh.exe >nul 2>nul && set "PS=pwsh.exe"
"%PS%" -NoProfile -ExecutionPolicy Bypass -File "%LAUNCHER%" %*
set "RC=%ERRORLEVEL%"
if not defined GAUFORGE_NO_PAUSE pause
exit /b %RC%
