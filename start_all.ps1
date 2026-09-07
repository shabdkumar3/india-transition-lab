# ============================================================
#  India Transition Lab -- Start All Services  (v2 -- bulletproof)
#
#  USAGE:
#    powershell -ExecutionPolicy Bypass -File start_all.ps1
#    powershell -ExecutionPolicy Bypass -File start_all.ps1 -KillFirst
# ============================================================

param(
    [switch]$KillFirst,   # -KillFirst : stop anything on our ports first
    [switch]$NoBrowser,   # -NoBrowser : dont auto-open browser
    [switch]$HealthOnly   # -HealthOnly : just report status
)

$Root = "D:\niti"
$FE   = "$Root\unified-frontend"

function OK   { param($m) Write-Host "  [OK] $m"  -ForegroundColor Green  }
function WARN { param($m) Write-Host "  [!!] $m"  -ForegroundColor Yellow }
function INFO { param($m) Write-Host "       $m"  -ForegroundColor Cyan   }
function HEAD { param($m) Write-Host "`n=== $m ===" -ForegroundColor Cyan  }

function Kill-Port {
    param([int]$Port)
    $hits = netstat -ano 2>$null |
        Select-String ":$Port\s" |
        ForEach-Object { ($_ -split '\s+')[-1] } |
        Where-Object   { $_ -match '^\d+$' -and $_ -ne '0' } |
        Sort-Object -Unique
    foreach ($pid in $hits) {
        try { Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue } catch {}
    }
}

function Is-Up {
    param([int]$Port, [string]$Path = "/health")
    try {
        $r = Invoke-WebRequest "http://localhost:$Port$Path" `
             -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
        return ($r.StatusCode -eq 200)
    } catch { return $false }
}

function Wait-Port {
    param([int]$Port, [string]$Label, [string]$Path = "/health", [int]$MaxSec = 90)
    $sw = [Diagnostics.Stopwatch]::StartNew()
    $dot = 0
    while ($sw.Elapsed.TotalSeconds -lt $MaxSec) {
        if (Is-Up $Port -Path $Path) {
            Write-Host ""
            OK "$Label is ready  ->  http://localhost:$Port"
            return $true
        }
        if ($dot++ % 5 -eq 0) { Write-Host -NoNewline "." -ForegroundColor DarkGray }
        Start-Sleep -Milliseconds 1500
    }
    Write-Host ""
    WARN "$Label did not respond in ${MaxSec}s -- check the minimised window"
    return $false
}

HEAD "India Transition Lab"
Write-Host "  5 sectors * CPS + NZS * static-first loading" -ForegroundColor White

if ($HealthOnly) {
    HEAD "Service Status"
    if (Is-Up 8000)           { OK  "Combined Backend  ->  http://localhost:8000" }
    else                      { WARN "Combined Backend     NOT responding on 8000" }
    if (Is-Up 3010 -Path "/") { OK  "Frontend          ->  http://localhost:3010" }
    else                      { WARN "Frontend             NOT responding on 3010" }
    exit 0
}

if ($KillFirst) {
    HEAD "Stopping existing services"
    foreach ($p in @(8000, 8001, 8002, 8003, 8004, 3010)) { Kill-Port $p }
    Start-Sleep -Seconds 2
    OK "All ports cleared"
}

HEAD "Starting Combined Backend (all 5 sectors, port 8000)"
if (Is-Up 8000) {
    OK "Already running"
} else {
    Kill-Port 8000
    Start-Process powershell `
        -ArgumentList "-NoExit", "-Command",
            "Set-Location '$Root'; `$Host.UI.RawUI.WindowTitle='ITL Backend :8000'; python combined_backend.py" `
        -WindowStyle Minimized
    $null = Wait-Port 8000 "Combined Backend" "/health" 90
}

HEAD "Starting Next.js Frontend (port 3010)"
$frontendReady = $false
if (Is-Up 3010 -Path "/") {
    OK "Already running"
    $frontendReady = $true
} else {
    Kill-Port 3010
    Start-Process powershell `
        -ArgumentList "-NoExit", "-Command",
            "Set-Location '$FE'; `$Host.UI.RawUI.WindowTitle='ITL Frontend :3010'; npm run dev -- --port 3010" `
        -WindowStyle Minimized
    $frontendReady = Wait-Port 3010 "Next.js Frontend" "/" 120
}

HEAD "Endpoints"
Write-Host "  http://localhost:3010          <- Open this in your browser" -ForegroundColor White
Write-Host "  http://localhost:8000/docs     <- Backend API docs" -ForegroundColor DarkGray

if (-not $NoBrowser) {
    Start-Sleep -Seconds 2
    Start-Process "http://localhost:3010"
    if ($frontendReady) { OK "Browser opened -> http://localhost:3010" }
    else { WARN "Browser opened -- Next.js may still be compiling, refresh in 10s" }
}

HEAD "Done"
Write-Host "  Tip: run with -KillFirst to restart everything cleanly" -ForegroundColor DarkGray
Write-Host ""
