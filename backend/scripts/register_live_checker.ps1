# Registers the scheduled task RegWatchLiveChecker on the always-on PC.
# It runs backend/scripts/live_checker.py at logon and restarts it if it stops
# (a second copy never starts while one runs). Log: data/live_checker.log.
# Do not also run the web backend with SCHEDULER_ENABLED=true on any machine.
$root = "F:\side-income\regwatch-bangladesh"
$py = "$root\.venv\Scripts\pythonw.exe"
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero)
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
$logon = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$again = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 30)
$action = New-ScheduledTaskAction -Execute $py -Argument "`"$root\backend\scripts\live_checker.py`"" -WorkingDirectory $root
Register-ScheduledTask -TaskName "RegWatchLiveChecker" -Action $action -Trigger @($logon, $again) -Settings $settings `
    -Principal $principal -Force -Description "Checks bb.org.bd for new circulars (every 10 min on working days, 09:00-19:00)." | Out-Null
Get-ScheduledTask -TaskName RegWatchLiveChecker | Select-Object TaskName, State
