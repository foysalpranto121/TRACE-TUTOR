<#
.SYNOPSIS
  Install TRACE Tutor as a Windows service that starts at boot and restarts if it dies,
  plus a daily backup task. Run from an elevated PowerShell.

.DESCRIPTION
  Uses NSSM (https://nssm.cc) when it is on the PATH or next to this script, because it gives
  a real service with log capture and automatic restart. Without NSSM it falls back to a
  Scheduled Task that runs at startup, which keeps the site up but does not restart it after
  a crash - install NSSM for a real cohort.

  Assumes: repository already built (frontend/dist present), backend/.env configured with
  DEBUG=0 and a real SECRET_KEY, PostgreSQL and Docker set to start automatically.

.EXAMPLE
  PS> Set-ExecutionPolicy -Scope Process Bypass
  PS> .\deploy\windows\install-service.ps1
  PS> .\deploy\windows\install-service.ps1 -Uninstall
#>
[CmdletBinding()]
param(
    [string]$ServiceName = 'TraceTutor',
    [string]$Listen = '0.0.0.0:8000',
    [int]$Threads = 8,
    [string]$Python = '',
    [string]$BackupTime = '02:30',
    [switch]$Uninstall
)

$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$backend = Join-Path $repo 'backend'
$logs = Join-Path $backend 'logs'
if (-not $Python) {
    $venv = Join-Path $backend '.venv\Scripts\python.exe'
    $Python = if (Test-Path $venv) { $venv } else { (Get-Command python).Source }
}
$nssm = Get-Command nssm -ErrorAction SilentlyContinue
if (-not $nssm -and (Test-Path (Join-Path $PSScriptRoot 'nssm.exe'))) { $nssm = Get-Item (Join-Path $PSScriptRoot 'nssm.exe') }
$taskName = "$ServiceName (startup)"
$backupTask = "$ServiceName backup"

function Assert-Admin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $p = New-Object Security.Principal.WindowsPrincipal($id)
    if (-not $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw 'Run this from an elevated (Administrator) PowerShell.'
    }
}
Assert-Admin

if ($Uninstall) {
    if ($nssm) { & $nssm.Source stop $ServiceName 2>$null; & $nssm.Source remove $ServiceName confirm 2>$null }
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $backupTask -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "Removed service/tasks for $ServiceName."
    return
}

New-Item -ItemType Directory -Force $logs | Out-Null
$args = "-m waitress --listen=$Listen --threads=$Threads trace_backend.wsgi:application"

Write-Host "Repository : $repo"
Write-Host "Python     : $Python"
Write-Host "Listen     : $Listen ($Threads threads)"

if ($nssm) {
    & $nssm.Source stop $ServiceName 2>$null | Out-Null
    & $nssm.Source remove $ServiceName confirm 2>$null | Out-Null
    & $nssm.Source install $ServiceName $Python $args
    & $nssm.Source set $ServiceName AppDirectory $backend
    & $nssm.Source set $ServiceName AppStdout (Join-Path $logs 'waitress.out.log')
    & $nssm.Source set $ServiceName AppStderr (Join-Path $logs 'waitress.err.log')
    & $nssm.Source set $ServiceName AppRotateFiles 1
    & $nssm.Source set $ServiceName AppRotateBytes 10485760
    & $nssm.Source set $ServiceName AppExit Default Restart
    & $nssm.Source set $ServiceName AppRestartDelay 5000
    & $nssm.Source set $ServiceName Start SERVICE_AUTO_START
    & $nssm.Source set $ServiceName DependOnService postgresql-x64-18
    & $nssm.Source set $ServiceName Description 'TRACE Tutor research platform (Django + built React app via waitress)'
    & $nssm.Source start $ServiceName
    Write-Host "Service '$ServiceName' installed and started (NSSM). Logs: $logs"
} else {
    Write-Warning 'NSSM not found: registering a startup task instead. It will not restart after a crash.'
    $action = New-ScheduledTaskAction -Execute $Python -Argument $args -WorkingDirectory $backend
    $trigger = New-ScheduledTaskTrigger -AtStartup
    $settings = New-ScheduledTaskSettingsSet -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew
    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -RunLevel Highest -User 'SYSTEM' -Force | Out-Null
    Start-ScheduledTask -TaskName $taskName
    Write-Host "Startup task '$taskName' registered and started."
}

# Daily backup: database dump + file stores into BACKUP_DIR (backend/.env), pruned to BACKUP_KEEP.
$bAction = New-ScheduledTaskAction -Execute $Python -Argument 'manage.py backup_study' -WorkingDirectory $backend
$bTrigger = New-ScheduledTaskTrigger -Daily -At $BackupTime
$bSettings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Hours 2) -StartWhenAvailable
Register-ScheduledTask -TaskName $backupTask -Action $bAction -Trigger $bTrigger -Settings $bSettings -RunLevel Highest -User 'SYSTEM' -Force | Out-Null
Write-Host "Backup task '$backupTask' registered daily at $BackupTime."

Start-Sleep -Seconds 4
try {
    $health = Invoke-RestMethod "http://127.0.0.1:$($Listen.Split(':')[-1])/api/health/" -TimeoutSec 10
    Write-Host "Health: $($health | ConvertTo-Json -Compress)"
} catch {
    Write-Warning "Health probe did not answer yet: $($_.Exception.Message). Check $logs."
}
