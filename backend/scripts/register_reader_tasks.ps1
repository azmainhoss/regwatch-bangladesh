# Registers two Windows scheduled tasks on the always-on PC (both start at logon and every 15/30 min;
# a second copy never starts while one runs):
#   RegWatchPageReader    - backend/scripts/read_pages.py: reads waiting Bangla/scanned pages with all keys
#   RegWatchArchiveImport - backend/scripts/import_archive.py --app-db: adds newly downloaded archive files
$root = "F:\side-income\regwatch-bangladesh"
$py = "$root\.venv\Scripts\pythonw.exe"
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero)
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
$logon = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME

$a1 = New-ScheduledTaskAction -Execute $py -Argument "`"$root\backend\scripts\read_pages.py`"" -WorkingDirectory $root
$r1 = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 15)
Register-ScheduledTask -TaskName "RegWatchPageReader" -Action $a1 -Trigger @($logon, $r1) -Settings $settings `
    -Principal $principal -Force -Description "Reads waiting Bangla and scanned circular pages with the free Gemini keys." | Out-Null

$a2 = New-ScheduledTaskAction -Execute $py -Argument "`"$root\backend\scripts\import_archive.py`" --app-db" -WorkingDirectory $root
$r2 = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(2) -RepetitionInterval (New-TimeSpan -Minutes 30)
Register-ScheduledTask -TaskName "RegWatchArchiveImport" -Action $a2 -Trigger @($logon, $r2) -Settings $settings `
    -Principal $principal -Force -Description "Adds newly downloaded archive circulars to the RegWatch library." | Out-Null

Get-ScheduledTask -TaskName RegWatchPageReader, RegWatchArchiveImport | Select-Object TaskName, State
