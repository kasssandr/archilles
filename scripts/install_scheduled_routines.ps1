# =============================================================================
# ARCHILLES Scheduled Routines - Installer
#
# Registers tasks in Windows Task Scheduler under the current user
# (NO admin rights required). Trigger: at every logon. Throttling is done
# by marker files inside each script (1x/day or 1x/ISO-week).
#
#   Archilles-Routine-Calibre    -> run_routine.py --source archilles --phase A (Metadaten-Stubs, schnell, täglich)
#   Archilles-Routine-Calibre-B  -> run_routine.py --source archilles --phase B (Volltext-Backlog, langsam, ohne Limit)
#   Archilles-Routine-Lab        -> run_routine.py --source archilles-lab    (Obsidian, täglich)
#   Archilles-Routine-Zotero     -> run_routine.py --source archilles-zotero (Zotero, täglich)
#   Archilles-Status-Mail        -> scripts/weekly_status_mail.py
#   Archilles-Vault-Linker       -> scripts/run_link_vault.py
#
# Reihenfolge bei Logon (Lock serialisiert alle Routinen):
#   PT5M  → Calibre-A, Lab, Zotero starten gemeinsam (schnell, je ~2-5 min)
#   PT25M → Calibre-B startet erst wenn die anderen Routinen typischerweise
#            fertig sind; läuft dann stundenlang bis CTRL+C oder fertig
#   PT15M → Status-Mail
#   PT30M → Vault-Linker
#
# Calibre-B:
#   * Kein max_new-Limit — läuft bis Rückstand leer oder manuell gestoppt
#   * CTRL+C (einmal): aktuelles Buch fertig indexieren, dann stoppen
#   * Checkpoint index_fulltext_checkpoint.json: nächster Lauf macht weiter
#   * Eigener Marker last_routine_run_phaseB.txt: läuft täglich bis Rückstand leer
#   * Unbegrenzte ExecutionTimeLimit (Task Scheduler tötet ihn nicht nach 8h)
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

# Phase B darf unbegrenzt laufen — kein 8h-Kill durch den Scheduler
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
    -Description "Calibre Phase A: Metadaten-Stubs fuer neue Buecher + Delta-Updates, max. 1x/Tag (schnell)" `
    -Arguments   @("`"$Runner`"", "--source", "archilles", "--frequency", "daily", "--phase", "A", "--wait-for-lock", "7200") `
    -Delay       "PT5M"

# Phase B hat eigene Settings (unbegrenzte Laufzeit) — direkt registrieren statt New-ArchillesTask
$actionB  = New-ScheduledTaskAction `
    -Execute          $Python `
    -Argument         ("`"$Runner`" --source archilles --frequency daily --phase B --wait-for-lock 7200") `
    -WorkingDirectory $RepoRoot
$triggerB = New-ScheduledTaskTrigger -AtLogOn -User $CurrentUser
$triggerB.Delay = "PT25M"
if (Get-ScheduledTask -TaskName "Archilles-Routine-Calibre-B" -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName "Archilles-Routine-Calibre-B" -Confirm:$false
}
Register-ScheduledTask `
    -TaskName    "Archilles-Routine-Calibre-B" `
    -Description "Calibre Phase B: Volltext-Backlog (Phase1-Stubs -> Volltext), laeuft bis fertig oder CTRL+C, kein Zeitlimit" `
    -Action      $actionB `
    -Trigger     $triggerB `
    -Settings    $SettingsB `
    -Principal   $Principal | Out-Null
Write-Host "  registered: Archilles-Routine-Calibre-B"

New-ArchillesTask `
    -Name        "Archilles-Routine-Lab" `
    -Description "Obsidian vault: index new documents, max. 1x per day" `
    -Arguments   @("`"$Runner`"", "--source", "archilles-lab", "--frequency", "daily", "--wait-for-lock", "7200") `
    -Delay       "PT5M"

New-ArchillesTask `
    -Name        "Archilles-Routine-Zotero" `
    -Description "Zotero library: index new documents, max. 1x per day" `
    -Arguments   @("`"$Runner`"", "--source", "archilles-zotero", "--frequency", "daily", "--wait-for-lock", "7200") `
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
