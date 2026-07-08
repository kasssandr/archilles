# =============================================================================
# ARCHILLES Scheduled Routines - Installer
#
# Registers tasks in Windows Task Scheduler under the current user
# (NO admin rights required). Trigger: at every logon. Throttling is done
# by marker files inside each script (once per day or once per ISO week).
#
#   Archilles-Routine-Calibre    -> run_routine.py --source archilles --phase A (metadata stubs + delta updates, fast)
#   Archilles-Routine-Calibre-B  -> run_routine.py --source archilles --phase B (full-text backlog, slow, no limit)
#   Archilles-Routine-Lab        -> run_routine.py --source archilles-lab    (Obsidian vault)
#   Archilles-Routine-Zotero     -> run_routine.py --source archilles-zotero (Zotero)
#   Archilles-Status-Mail        -> scripts/weekly_status_mail.py
#   Archilles-Vault-Linker       -> scripts/run_link_vault.py
#
# Default cadence: Zotero and Obsidian vault daily, Calibre (both phases)
# weekly. Override per machine via parameters, e.g. for an annotation-heavy
# Calibre workflow:
#
#   .\install_scheduled_routines.ps1 -CalibreFrequency daily
#
# Python and repo root are auto-detected (first "python" on PATH; parent of
# this script's directory) and can likewise be overridden via -PythonPath /
# -RepoRoot. Re-running the installer is safe: existing Archilles-* tasks
# are replaced.
#
# Logon order (a runtime lock serialises all routines):
#   PT5M  -> Calibre-A, Lab, Zotero start together (fast, ~2-5 min each)
#   PT25M -> Calibre-B starts once the others are typically done; may then
#            run for hours until the backlog is drained or CTRL+C
#   PT15M -> Status mail
#   PT30M -> Vault linker
#
# Calibre-B:
#   * No max_new limit - runs until the backlog is empty or stopped manually
#   * CTRL+C (once): finish indexing the current book, then stop
#   * Checkpoint index_fulltext_checkpoint.json: the next run resumes
#   * Own marker last_routine_run_phaseB.txt (same cadence as Phase A)
#   * Unlimited ExecutionTimeLimit (Task Scheduler will not kill it after 8h)
#
# Uninstall later:
#   Get-ScheduledTask -TaskName 'Archilles-*' | Unregister-ScheduledTask -Confirm:$false
#
# =============================================================================

param(
    # Python interpreter used by all tasks. Default: first "python" on PATH.
    [string]$PythonPath,
    # Repository root. Default: parent of the directory this script lives in.
    [string]$RepoRoot,
    [ValidateSet("daily", "weekly")] [string]$CalibreFrequency = "weekly",
    [ValidateSet("daily", "weekly")] [string]$ZoteroFrequency = "daily",
    [ValidateSet("daily", "weekly")] [string]$LabFrequency = "daily"
)

$ErrorActionPreference = "Stop"

if (-not $PythonPath) {
    $PythonPath = (Get-Command python -ErrorAction SilentlyContinue).Source
    if (-not $PythonPath) {
        throw "No 'python' found on PATH - pass -PythonPath explicitly."
    }
}
if (-not $RepoRoot) {
    $RepoRoot = Split-Path $PSScriptRoot -Parent
}

$Runner   = Join-Path $RepoRoot "scripts\run_routine.py"
$Mailer   = Join-Path $RepoRoot "scripts\weekly_status_mail.py"
$Linker   = Join-Path $RepoRoot "scripts\run_link_vault.py"

foreach ($p in @($PythonPath, $Runner, $Mailer, $Linker, $RepoRoot)) {
    if (-not (Test-Path $p)) { throw "Path not found: $p" }
}

$Settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -DontStopOnIdleEnd `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Hours 8)

# Phase B may run without limit - no 8h kill by the scheduler
$SettingsB = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -DontStopOnIdleEnd `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit ([System.TimeSpan]::Zero)

$CurrentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name

$Principal = New-ScheduledTaskPrincipal `
    -UserId    $CurrentUser `
    -LogonType Interactive `
    -RunLevel  Limited

function New-ArchillesTask {
    param(
        [Parameter(Mandatory)] [string]   $Name,
        [Parameter(Mandatory)] [string]   $Description,
        [Parameter(Mandatory)] [string[]] $Arguments,
        [Parameter(Mandatory)] [string]   $Delay
    )

    $action = New-ScheduledTaskAction `
        -Execute          $PythonPath `
        -Argument         ($Arguments -join ' ') `
        -WorkingDirectory $RepoRoot

    $trigger = New-ScheduledTaskTrigger -AtLogOn -User $CurrentUser
    $trigger.Delay = $Delay

    if (Get-ScheduledTask -TaskName $Name -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $Name -Confirm:$false
    }

    Register-ScheduledTask `
        -TaskName    $Name `
        -Description $Description `
        -Action      $action `
        -Trigger     $trigger `
        -Settings    $Settings `
        -Principal   $Principal | Out-Null

    Write-Host ("  registered: {0}" -f $Name)
}

Write-Host "ARCHILLES Scheduled Routines - Installation"
Write-Host "User:    $CurrentUser"
Write-Host "Python:  $PythonPath"
Write-Host "Repo:    $RepoRoot"
Write-Host "Cadence: Calibre=$CalibreFrequency, Zotero=$ZoteroFrequency, Vault=$LabFrequency"
Write-Host ""

New-ArchillesTask `
    -Name        "Archilles-Routine-Calibre" `
    -Description "Calibre Phase A: metadata stubs for new books + delta updates, max. 1x/$CalibreFrequency (fast)" `
    -Arguments   @("`"$Runner`"", "--source", "archilles", "--frequency", $CalibreFrequency, "--phase", "A", "--wait-for-lock", "7200") `
    -Delay       "PT5M"

# Phase B has its own settings (unlimited runtime) - register directly instead of New-ArchillesTask
$actionB  = New-ScheduledTaskAction `
    -Execute          $PythonPath `
    -Argument         ("`"$Runner`" --source archilles --frequency $CalibreFrequency --phase B --wait-for-lock 7200") `
    -WorkingDirectory $RepoRoot
$triggerB = New-ScheduledTaskTrigger -AtLogOn -User $CurrentUser
$triggerB.Delay = "PT25M"
if (Get-ScheduledTask -TaskName "Archilles-Routine-Calibre-B" -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName "Archilles-Routine-Calibre-B" -Confirm:$false
}
Register-ScheduledTask `
    -TaskName    "Archilles-Routine-Calibre-B" `
    -Description "Calibre Phase B: full-text backlog (phase1 stubs -> full text), runs until done or CTRL+C, no time limit" `
    -Action      $actionB `
    -Trigger     $triggerB `
    -Settings    $SettingsB `
    -Principal   $Principal | Out-Null
Write-Host "  registered: Archilles-Routine-Calibre-B"

New-ArchillesTask `
    -Name        "Archilles-Routine-Lab" `
    -Description "Obsidian vault: index new documents, max. 1x/$LabFrequency" `
    -Arguments   @("`"$Runner`"", "--source", "archilles-lab", "--frequency", $LabFrequency, "--wait-for-lock", "7200") `
    -Delay       "PT5M"

New-ArchillesTask `
    -Name        "Archilles-Routine-Zotero" `
    -Description "Zotero library: watchdog scan, max. 1x/$ZoteroFrequency" `
    -Arguments   @("`"$Runner`"", "--source", "archilles-zotero", "--frequency", $ZoteroFrequency, "--wait-for-lock", "7200") `
    -Delay       "PT5M"

New-ArchillesTask `
    -Name        "Archilles-Status-Mail" `
    -Description "Weekly status mail (first logon of the new ISO week)" `
    -Arguments   @("`"$Mailer`"") `
    -Delay       "PT15M"

New-ArchillesTask `
    -Name        "Archilles-Vault-Linker" `
    -Description "Obsidian vault MOC + cross-link maintenance, monthly. Hard-gated on completed Lab routine of the same day." `
    -Arguments   @("`"$Linker`"") `
    -Delay       "PT30M"

Write-Host ""
Write-Host "Done. Show status with:"
Write-Host "  Get-ScheduledTask -TaskName 'Archilles-*' | Format-Table TaskName, State"
