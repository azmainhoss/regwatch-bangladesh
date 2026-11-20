# Syncs the shared analysis work repo with the app (runs hourly as the Windows task RegWatchAnalysisSync).
#  1. pulls answers written by the cloud runs and loads new ones into the app (same checks as a live model);
#  2. adds circulars whose pages have finished reading to the repo's inbox and queue, and pushes them.
# Needs no extra account: it only uses git and the app's own Python.
$ErrorActionPreference = "Continue"
$app = "F:\side-income\regwatch-bangladesh"
$repo = "F:\side-income\regwatch-analysis-work"
$py = "$app\.venv\Scripts\python.exe"
$log = "$app\research\archive\data\manual_analysis\sync.log"

function Log($m) { Add-Content -Path $log -Value ("{0}  {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $m) -Encoding utf8 }

Set-Location $repo
git pull --rebase --quiet 2>&1 | ForEach-Object { Log "pull: $_" }

# Cloud runs may only be allowed to push to their own branch. Copy any answer that exists on another
# branch but not on main onto main, so both lanes and this PC see it.
git fetch --all --prune --quiet 2>&1 | ForEach-Object { Log "fetch: $_" }
$copied = 0
foreach ($br in (git branch -r --format "%(refname:short)" | Where-Object { $_ -notmatch "/(main|HEAD)$" -and $_ -ne "origin" })) {
    foreach ($f in (git ls-tree --name-only "$br" answers/ 2>$null | Where-Object { $_ -like "answers/*.json" })) {
        if (-not (Test-Path (Join-Path $repo $f))) {
            $bytes = [System.Text.Encoding]::UTF8.GetBytes(((git show "${br}:$f") -join "`n"))
            [System.IO.File]::WriteAllBytes((Join-Path $repo $f), $bytes)
            git add $f
            $copied++
        }
    }
    foreach ($f in @("RUNLOG.md", "SKIPPED.md")) {
        $theirs = git show "${br}:$f" 2>$null
        if ($theirs) {
            $mine = Get-Content (Join-Path $repo $f) -Encoding utf8
            $new = $theirs | Where-Object { $_ -and ($mine -notcontains $_) }
            if ($new) { Add-Content -Path (Join-Path $repo $f) -Value $new -Encoding utf8; git add $f }
        }
    }
}
if ($copied -gt 0) {
    git commit --quiet -m "Collect analyses from run branches"
    git push --quiet 2>&1 | ForEach-Object { Log "push: $_" }
    Log "copied $copied answer(s) from run branches to main"
}

Set-Location $app
$out = & $py backend\scripts\manual_analysis.py pull --repo $repo 2>&1 | Where-Object { $_ -match "loaded|failed|not loaded|Loaded|No new" }
$out | ForEach-Object { Log "load: $_" }
$out = & $py backend\scripts\manual_analysis.py export --repo $repo 2>&1 | Where-Object { $_ -match "^Exported" }
$out | ForEach-Object { Log "export: $_" }

Set-Location $repo
git add inbox inbox_long QUEUE.txt INSTRUCTIONS.md check.py 2>$null
git diff --cached --quiet
if ($LASTEXITCODE -ne 0) {
    git commit --quiet -m "Add newly read circulars"
    git pull --rebase --quiet 2>&1 | ForEach-Object { Log "pull: $_" }
    git push --quiet 2>&1 | ForEach-Object { Log "push: $_" }
    Log "pushed new circulars"
}
