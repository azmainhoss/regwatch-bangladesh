# Registers the Windows task RegWatchPhase1Sync: twice a day (09:30 and 15:30 Bangladesh time) it queues the
# server's new circulars for the Claude runs and uploads finished analyses (backend/scripts/phase1_sync.py).
# Run once in PowerShell from the repo folder. Set REGWATCH_SERVER_URL and REGWATCH_UPLOAD_TOKEN in .env first.
$ErrorActionPreference = "Stop"
$app = (Resolve-Path "$PSScriptRoot\..\..").Path
$repo = if ($env:REGWATCH_WORK_REPO) { $env:REGWATCH_WORK_REPO } else { "F:\side-income\regwatch-analysis-work" }
$py = Join-Path $app ".venv\Scripts\python.exe"
$args = "`"$app\backend\scripts\phase1_sync.py`" sync --repo `"$repo`""
$action = New-ScheduledTaskAction -Execute $py -Argument $args -WorkingDirectory $app
$triggers = @(
  (New-ScheduledTaskTrigger -Daily -At "09:30"),
  (New-ScheduledTaskTrigger -Daily -At "15:30")
)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 1) -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName "RegWatchPhase1Sync" -Action $action -Trigger $triggers -Settings $settings -Description "RegWatch Phase 1: queue new circulars for Claude and upload finished analyses" -Force | Out-Null
Write-Host "Registered RegWatchPhase1Sync (09:30 and 15:30, laptop clock = Bangladesh time). Repo: $repo"
Write-Host "Run it once now to check: schtasks /run /tn RegWatchPhase1Sync, then read data\phase1_sync.log"
