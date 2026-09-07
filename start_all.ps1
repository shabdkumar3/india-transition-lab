# ============================================================
#  India Transition Lab -- Start All Services
#  Run from D:\niti:
#    powershell -ExecutionPolicy Bypass -File start_all.ps1
#
#  Starts:
#    Steel backend    -> http://localhost:8000   (MILP webapp)
#    Cement backend   -> http://localhost:8001   (v3 annual LP)
#    Aluminium backend-> http://localhost:8002   (v3 annual LP)
#    Textile backend  -> http://localhost:8003   (v3 annual LP)
#    Fertiliser backend->http://localhost:8004   (v3 annual LP)
#    Unified frontend -> http://localhost:3010   (Next.js)
# ============================================================

param(
    [switch]$KillFirst,     # Pass -KillFirst to stop any running instances first
    [switch]$NoBrowser,     # Pass -NoBrowser to skip auto-opening the browser
    [switch]$HealthOnly     # Pass -HealthOnly to just check status without starting
)

$Root    = "D:\niti"
$FE      = "$Root\unified-frontend"
$Backends= "$Root\sector-backends"
$Steel   = "$Root\steel-transition-model"

$Ports = @(8000, 8001, 8002, 8003, 8004, 3010)

# -- Colours -------------------------------------------------
function OK    { param($m) Write-Host "  [OK]  $m" -ForegroundColor Green  }
function WARN  { param($m) Write-Host "  [!!]  $m" -ForegroundColor Yellow }
function ERR   { param($m) Write-Host "  [XX]  $m" -ForegroundColor Red    }
function INFO  { param($m) Write-Host "        $m" -ForegroundColor Gray   }
function HEAD  { param($m) Write-Host "`n$m" -ForegroundColor Cyan         }

# -- Kill existing processes on our ports -------------------
function Stop-PortProcess {
    param([int]$Port)
    $pids = (netstat -ano 2>$null | Select-String ":$Port\s") |
        ForEach-Object { ($_ -split '\s+')[-1] } | Sort-Object -Unique
    foreach ($p in $pids) {
        if ($p -match '^\d+$' -and $p -ne '0') {
            try { Stop-Process -Id $p -Force -ErrorAction SilentlyContinue } catch {}
        }
    }
}

function Test-Port {
    param([int]$Port)
    try {
        $r = Invoke-RestMethod "http://localhost:$Port/health" -TimeoutSec 3 -ErrorAction Stop
        return $true
    } catch {
        return $false
    }
}

# ============================================================
HEAD "India Transition Lab"
Write-Host "  5 sectors * 26 routes * CPS + NZS scenarios" -ForegroundColor White
Write-Host "  NITI Aayog (2026) Vol.4 - Viksit Bharat Net Zero" -ForegroundColor DarkGray

# -- Health-only mode ----------------------------------------
if ($HealthOnly) {
    HEAD "Service Status"
    $names = @{ 8000="Steel (MILP)"; 8001="Cement"; 8002="Aluminium"; 8003="Textile"; 8004="Fertiliser"; 3010="Frontend" }
    foreach ($port in $Ports) {
        if (Test-Port $port) { OK "$($names[$port]) -> http://localhost:$port" }
        else                  { ERR "$($names[$port]) -> http://localhost:$port  (not responding)" }
    }
    exit 0
}

# -- Kill first if requested ---------------------------------
if ($KillFirst) {
    HEAD "Stopping existing services..."
    foreach ($p in $Ports) {
        Stop-PortProcess $p
        INFO "Cleared port $p"
    }
    Start-Sleep -Seconds 2
}

# ============================================================
HEAD "Starting backends..."

# -- 1. Steel (MILP webapp, port 8000) ---------------------
if (-not (Test-Port 8000)) {
    Write-Host "  [1/6] Steel backend (port 8000)..." -ForegroundColor Yellow
    Start-Process powershell -ArgumentList "-NoExit", "-Command",
        "cd '$Steel'; `$Host.UI.RawUI.WindowTitle='ITL Steel :8000'; python -m uvicorn webapp.app.main:app --host 0.0.0.0 --port 8000 --reload" `
        -WindowStyle Minimized
} else {
    OK "Steel already running on 8000"
}

# -- 2-5. Sector v3 backends --------------------------------
$sectorBackends = @(
    @{ n="Cement";     f="cement_backend_v3.py";     p=8001 },
    @{ n="Aluminium";  f="aluminium_backend_v3.py";  p=8002 },
    @{ n="Textile";    f="textile_backend_v3.py";    p=8003 },
    @{ n="Fertiliser"; f="fertiliser_backend_v3.py"; p=8004 }
)

$i = 2
foreach ($sb in $sectorBackends) {
    if (-not (Test-Port $sb.p)) {
        Write-Host "  [$i/6] $($sb.n) backend v3 (port $($sb.p))..." -ForegroundColor Yellow
        Start-Process powershell -ArgumentList "-NoExit", "-Command",
            "`$Host.UI.RawUI.WindowTitle='ITL $($sb.n) :$($sb.p)'; python '$Backends\$($sb.f)'" `
            -WindowStyle Minimized
    } else {
        OK "$($sb.n) already running on $($sb.p)"
    }
    $i++
}

# -- 6. Unified Frontend (Next.js port 3010) ---------------
if (-not (Test-Port 3010)) {
    Write-Host "  [6/6] Unified frontend (port 3010)..." -ForegroundColor Yellow
    Start-Process powershell -ArgumentList "-NoExit", "-Command",
        "cd '$FE'; `$Host.UI.RawUI.WindowTitle='ITL Frontend :3010'; npm run dev -- --port 3010" `
        -WindowStyle Minimized
} else {
    OK "Frontend already running on 3010"
}

# ============================================================
HEAD "Waiting for services (up to 30s)..."

$deadline = (Get-Date).AddSeconds(30)
$ready = @{}
$allPorts = @{ 8000="Steel"; 8001="Cement"; 8002="Aluminium"; 8003="Textile"; 8004="Fertiliser"; 3010="Frontend" }

while ((Get-Date) -lt $deadline) {
    $stillWaiting = $false
    foreach ($port in $Ports) {
        if (-not $ready[$port]) {
            if (Test-Port $port) {
                $ready[$port] = $true
                OK "$($allPorts[$port]) ready -> http://localhost:$port"
            } else {
                $stillWaiting = $true
            }
        }
    }
    if (-not $stillWaiting) { break }
    Start-Sleep -Seconds 2
    Write-Host "  ..." -ForegroundColor DarkGray
}

# -- Final status --------------------------------------------
HEAD "Final Status"
$allOK = $true
foreach ($port in $Ports) {
    if ($ready[$port]) {
        OK "$($allPorts[$port]) :$port"
    } else {
        WARN "$($allPorts[$port]) :$port - still starting (check minimised window)"
        $allOK = $false
    }
}

HEAD "Endpoints"
Write-Host "  Frontend     -> http://localhost:3010" -ForegroundColor Cyan
Write-Host "  Steel API    -> http://localhost:8000/docs" -ForegroundColor DarkCyan
Write-Host "  Cement API   -> http://localhost:8001/docs" -ForegroundColor DarkCyan
Write-Host "  Aluminium API-> http://localhost:8002/docs" -ForegroundColor DarkCyan
Write-Host "  Textile API  -> http://localhost:8003/docs" -ForegroundColor DarkCyan
Write-Host "  Fertiliser API->http://localhost:8004/docs" -ForegroundColor DarkCyan
Write-Host ""
Write-Host "  Sectors:  /steel  /cement  /aluminium  /textile  /fertiliser" -ForegroundColor White
Write-Host ""
Write-Host "  Tip: run with -KillFirst to restart everything from scratch" -ForegroundColor DarkGray
Write-Host "       run with -HealthOnly to just check status" -ForegroundColor DarkGray
Write-Host ""

# -- Open browser --------------------------------------------
if (-not $NoBrowser -and $ready[3010]) {
    Start-Sleep -Seconds 1
    Start-Process "http://localhost:3010"
    INFO "Browser opened -> http://localhost:3010"
}

if ($allOK) {
    Write-Host "`n  All 6 services running. Enjoy the lab!" -ForegroundColor Green
} else {
    Write-Host "`n  Some services still warming up - check minimised PowerShell windows." -ForegroundColor Yellow
}
