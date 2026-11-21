$p = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'cmd.exe" /k .*uvicorn backend.app.main' }
foreach ($x in $p) { taskkill /PID $x.ProcessId /T /F | Out-Null }
Start-Sleep 2
Start-Process cmd -ArgumentList '/k','title RegWatch backend&& set PYTHONUTF8=1&& set PYTHONIOENCODING=utf-8&& .venv\Scripts\python.exe -m uvicorn backend.app.main:app --port 8000' -WorkingDirectory 'F:\side-income\regwatch-bangladesh' -WindowStyle Minimized
