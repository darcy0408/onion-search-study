# One repetition of the Study 1 measurement, written to a dated file.
#
# Repetitions must be spread across DAYS, not run back-to-back. Find Tor
# failed 10/10 requests one day and succeeded 20/20 the next with no known
# change -- same-day repeats just re-measure the same network weather.
#
# Registered as a daily Windows Scheduled Task.

$ErrorActionPreference = "Continue"
$date    = Get-Date -Format "yyyy-MM-dd"
$outFile = "/app/research/data/raw/rep-$date.jsonl"
$logFile = Join-Path $PSScriptRoot "data\raw\schedule.log"

function Log($m) {
    $line = "{0}  {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $m
    Add-Content -Path $logFile -Value $line -Encoding utf8
}

Log "=== rep start ($date) ==="

# Container may be stopped after a reboot; restart policy should handle it,
# but start explicitly in case it was stopped by hand.
$state = (docker inspect robin --format '{{.State.Running}}' 2>$null)
if ($state -ne "true") {
    Log "container not running; starting"
    docker start robin | Out-Null
}

# Tor needs to bootstrap before any query will succeed. Poll rather than
# sleeping a fixed amount.
$ready = $false
for ($i = 0; $i -lt 40; $i++) {
    $logs = docker logs --tail 200 robin 2>&1 | Out-String
    if ($logs -match "Bootstrapped 100%") { $ready = $true; break }
    Start-Sleep -Seconds 5
}
if (-not $ready) {
    Log "ABORT: Tor did not reach 100% within 200s"
    exit 1
}
Log "Tor ready"

# --out is per-day, so the harness's resume logic protects within a day
# (crash-safe) without skipping across days.
docker exec robin python //app/research/harness.py `
    --out $outFile --null 5 --target 5 --common 10 --workers 4 2>&1 |
    ForEach-Object { Log $_ }

Log "=== rep done ==="
