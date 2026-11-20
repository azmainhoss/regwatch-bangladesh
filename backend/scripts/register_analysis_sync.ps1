# Registers the Windows scheduled task RegWatchAnalysisSync: every hour, sync_analysis_repo.ps1 loads new answers
# from the shared analysis repo into the app and pushes newly read circulars to it. A second copy never starts while
# one runs. Needs no extra account.
$script = "F:\side-income\regwatch-bangladesh\backend\scripts\sync_analysis_repo.ps1"
$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$script`""
$repeat = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(2) -RepetitionInterval (New-TimeSpan -Hours 1)
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 50)
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName "RegWatchAnalysisSync" -Action $action -Trigger $repeat `
    -Settings $settings -Principal $principal -Force `
    -Description "Loads analyses from the shared work repo into RegWatch (backend/scripts/sync_analysis_repo.ps1)." | Out-Null
Get-ScheduledTask -TaskName RegWatchAnalysisSync | Select-Object TaskName, State
