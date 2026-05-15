# =============================================================================
# ARCHILLES Scheduled Routines - Installer
#
# Registers four tasks in Windows Task Scheduler under the current user
# (NO admin rights required). Trigger: at every logon. Throttling is done
# by marker files inside each script (1x/day or 1x/ISO-week).
#
#   Archilles-Routine-Calibre  -> scripts/run_routine.py        --source archilles        --frequency daily
#   Archilles-Routine-Lab      -> scripts/run_routine.py        --source archilles-lab    --frequency daily
#   Archilles-Routine-Zotero   -> scripts/run_routine.py        --source archilles-zotero --frequency daily
#   Archilles-Status-Mail      -> scripts/weekly_status_mail.py
#
# Behaviour:
#   * 5 minute delay after logon (routines), 10 minutes (mail) - so login
#     itself is not slowed down; mail runs AFTER routines so latest stats
#     are included.
#   * If a logon trigger is missed (machine off): task starts at next logon.
#     Marker logic in the script prevents duplicate runs.
#   * Task runs as user (not admin).
#
# Uninstall later:
#   Get-ScheduledTask -TaskName 'Archilles-*' | Unregister-ScheduledTask -Confirm:$false
#
# =============================================================================

$ErrorActionPreference = "Stop"

$Python   = "C:\Users\tomra\AppData\Local\Programs\Python\Python312\python.exe"
$RepoRoot = "C:\Users\tomra\archilles"
$Runner   = Join-Path $RepoRoot "scripts\run_routine.py"
$Mailer   = Join-Path $RepoRoot "scripts\weekly_status_mail.py"
$Linker   = Join-Path $RepoRoot "scripts\run_link_vault.py"

foreach ($p in @($Python, $Runner, $Mailer, $Linker, $RepoRoot)) {
    if (-not (Test-Path $p)) { throw "Pfad nicht gefunden: $p" }
}

$Settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -DontStopOnIdleEnd `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Hours 8)

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
        -Execute          $Python `
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
Write-Host "Python:  $Python"
Write-Host "Repo:    $RepoRoot"
Write-Host ""

New-ArchillesTask `
    -Name        "Archilles-Routine-Calibre" `
    -Description "Calibre watchdog (hash diff, new + changed books), max. 1x per day" `
    -Arguments   @("`"$Runner`"", "--source", "archilles", "--frequency", "daily") `
    -Delay       "PT5M"

New-ArchillesTask `
    -Name        "Archilles-Routine-Lab" `
    -Description "Obsidian vault: index new documents, max. 1x per day" `
    -Arguments   @("`"$Runner`"", "--source", "archilles-lab", "--frequency", "daily") `
    -Delay       "PT5M"

New-ArchillesTask `
    -Name        "Archilles-Routine-Zotero" `
    -Description "Zotero library: index new documents, max. 1x per day" `
    -Arguments   @("`"$Runner`"", "--source", "archilles-zotero", "--frequency", "daily") `
    -Delay       "PT5M"

New-ArchillesTask `
    -Name        "Archilles-Status-Mail" `
    -Description "Weekly status mail (first logon of the new ISO week)" `
    -Arguments   @("`"$Mailer`"") `
    -Delay       "PT10M"

New-ArchillesTask `
    -Name        "Archilles-Vault-Linker" `
    -Description "Obsidian vault MOC + cross-link maintenance, monthly. Hard-gated on completed Lab routine of the same day." `
    -Arguments   @("`"$Linker`"") `
    -Delay       "PT30M"

Write-Host ""
Write-Host "Done. Show status with:"
Write-Host "  Get-ScheduledTask -TaskName 'Archilles-*' | Format-Table TaskName, State"
