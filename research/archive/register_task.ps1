# Registers the Windows scheduled task RegWatchArchiveDownload (runs 24/7, restarts if it stops).
# It starts at logon and every 15 minutes after that; a second copy never starts while one is running,
# and the script exits at once when the download is DONE or STOPPED (blocks).
# Does not touch RegWatchDetectPoll / RegWatchDetectReconcile.
$py = "E:\regwatch-research\venv\Scripts\pythonw.exe"
$script = "F:\side-income\regwatch-bangladesh\research\archive\fetch_all.py"
$dir = "F:\side-income\regwatch-bangladesh\research\archive"

$action = New-ScheduledTaskAction -Execute $py -Argument "`"$script`" run" -WorkingDirectory $dir
$logon = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$repeat = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 15)
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1)
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName "RegWatchArchiveDownload" -Action $action -Trigger @($logon, $repeat) `
    -Settings $settings -Principal $principal -Force `
    -Description "Downloads the Bangladesh Bank circular archive slowly (research/archive/fetch_all.py)." | Out-Null
Get-ScheduledTask -TaskName RegWatchArchiveDownload | Select-Object TaskName, State
