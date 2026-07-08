#requires -Version 5.1
<#
.SYNOPSIS
    GitHub AI Agent - One-click launcher (PowerShell).

.DESCRIPTION
    Brings up the whole stack so you only run this single script:
      1. Pre-flight checks (.env, GITHUB_TOKEN, venv)
      2. PostgreSQL  - start the local Windows service, wait for port 5432
      3. Ollama      - start `ollama serve` if needed, pull the model if missing
      4. Database    - create/update tables (init_db.py)
      5. FastAPI     - background process on :8000 (logs stream to this console)
      6. Next.js     - background dev server on :3000 (logs stream to this console)
      7. Wait until both are ready, open the dashboard, keep alive (Ctrl+C to stop)

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\start.ps1
#>

[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

# ── Paths ──────────────────────────────────────────────────────
$ProjectDir   = $PSScriptRoot
$VenvPython   = Join-Path $ProjectDir "venv\Scripts\python.exe"
$DashboardDir = Join-Path $ProjectDir "dashboard"

$OllamaModel    = "qwen3-coder:30b"
$OllamaPort     = 11434
$PostgresPort   = 5432
$ApiUrl         = "http://127.0.0.1:8000/docs"
$DashboardUrl   = "http://127.0.0.1:3000/"
$StartupTimeout = 120   # seconds

# Track child processes we own, so Ctrl+C can tear down their whole tree.
$script:OwnedProcs = @()

# ── Pretty output ──────────────────────────────────────────────
function Write-Banner {
    Write-Host ""
    Write-Host "  ╔══════════════════════════════════════════════════╗" -ForegroundColor Cyan
    Write-Host "  ║          🤖 GitHub AI Agent - Launcher           ║" -ForegroundColor Cyan
    Write-Host "  ╚══════════════════════════════════════════════════╝" -ForegroundColor Cyan
    Write-Host ""
}
function Write-Step($n, $total, $msg) { Write-Host ("  [{0}/{1}] {2}" -f $n, $total, $msg) -ForegroundColor Cyan }
function Write-Ok($msg = "")          { Write-Host ("    ✓ {0}" -f $msg) -ForegroundColor Green }
function Write-Warn($msg)             { Write-Host ("    ⚠ {0}" -f $msg) -ForegroundColor Yellow }
function Write-Err($msg)              { Write-Host ("    ✗ {0}" -f $msg) -ForegroundColor Red }

$TotalSteps = 7

# ── Helpers ────────────────────────────────────────────────────
function Test-Port {
    param([string]$TargetHost = "127.0.0.1", [int]$Port)
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $iar = $client.BeginConnect($TargetHost, $Port, $null, $null)
        if ($iar.AsyncWaitHandle.WaitOne(1000) -and $client.Connected) { return $true }
        return $false
    } catch {
        return $false
    } finally {
        $client.Close()
    }
}

function Wait-Port {
    param([int]$Port, [int]$TimeoutSec = 30, [string]$Label = "service")
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        if (Test-Port -Port $Port) { return $true }
        Start-Sleep -Milliseconds 700
    }
    return $false
}

function Test-HttpOk {
    param([string]$Url)
    try {
        $resp = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2
        return $resp.StatusCode -eq 200
    } catch {
        return $false
    }
}

function Stop-OwnedProcs {
    Write-Host ""
    Write-Host "  🛑 Shutting down servers..." -ForegroundColor DarkGray
    foreach ($p in $script:OwnedProcs) {
        if ($null -ne $p -and -not $p.HasExited) {
            # taskkill /T kills the whole child tree (npm -> next-dev node children).
            & taskkill /F /T /PID $p.Id 2>$null | Out-Null
        }
    }
    Write-Host "  👋 See you soon!" -ForegroundColor Green
    Write-Host ""
}

# ════════════════════════════════════════════════════════════════
# 1. Pre-flight checks
# ════════════════════════════════════════════════════════════════
function Invoke-PreChecks {
    Write-Step 1 $TotalSteps "Running pre-flight checks..."
    $errors = @()

    $envPath = Join-Path $ProjectDir ".env"
    if (-not (Test-Path $envPath)) {
        $errors += ".env file not found! Copy the .env.example file."
    } else {
        $tokenLine = Select-String -Path $envPath -Pattern '^\s*GITHUB_TOKEN\s*=\s*(.+)$' -ErrorAction SilentlyContinue
        $tokenVal = if ($tokenLine) { $tokenLine.Matches[0].Groups[1].Value.Trim() } else { "" }
        if (-not $tokenVal -or $tokenVal -eq "ghp_YOUR_TOKEN_HERE") {
            $errors += "GITHUB_TOKEN is not set! Edit the .env file."
        }
    }

    if (-not (Test-Path $VenvPython)) {
        $errors += "Virtual environment not found (venv\Scripts\python.exe). Run 'python -m venv venv'."
    }

    if ($errors.Count -gt 0) {
        Write-Err "Pre-flight checks failed!"
        foreach ($e in $errors) { Write-Host "      • $e" -ForegroundColor Red }
        exit 1
    }
    Write-Ok
}

# ════════════════════════════════════════════════════════════════
# 2. PostgreSQL (local Windows service)
# ════════════════════════════════════════════════════════════════
function Start-Postgres {
    Write-Step 2 $TotalSteps "Starting PostgreSQL..."

    if (Test-Port -Port $PostgresPort) {
        Write-Ok "Already running (port $PostgresPort)."
        return
    }

    $svc = Get-Service -Name 'postgresql*' -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $svc) {
        Write-Warn "PostgreSQL Windows service not found. Start the DB manually (port $PostgresPort)."
        return
    }

    if ($svc.Status -ne 'Running') {
        try {
            Start-Service -Name $svc.Name -ErrorAction Stop
        } catch {
            Write-Warn "Failed to start service ($($svc.Name)). Administrator rights may be required: $($_.Exception.Message)"
            return
        }
    }

    if (Wait-Port -Port $PostgresPort -TimeoutSec 30 -Label "PostgreSQL") {
        Write-Ok "$($svc.Name) is running (port $PostgresPort)."
    } else {
        Write-Warn "PostgreSQL service started but port $PostgresPort did not respond."
    }
}

# ════════════════════════════════════════════════════════════════
# 3. Ollama (serve + auto-pull)
# ════════════════════════════════════════════════════════════════
function Start-Ollama {
    Write-Step 3 $TotalSteps "Preparing Ollama ($OllamaModel)..."

    $ollama = Get-Command ollama -ErrorAction SilentlyContinue
    if (-not $ollama) {
        Write-Warn "'ollama' command not found in PATH. Install it from https://ollama.com/download."
        return
    }

    # Ensure the server is up.
    if (-not (Test-Port -Port $OllamaPort)) {
        # Hidden window: ollama serve output is too chatty for the shared console.
        Start-Process -FilePath "ollama" -ArgumentList "serve" -WindowStyle Hidden | Out-Null
        if (Wait-Port -Port $OllamaPort -TimeoutSec 30 -Label "Ollama") {
            Write-Ok "ollama serve started (port $OllamaPort)."
        } else {
            Write-Warn "ollama serve started but port $OllamaPort did not respond."
            return
        }
    } else {
        Write-Ok "Ollama already running (port $OllamaPort)."
    }

    # Ensure the model is present.
    $models = (& ollama list 2>$null) -join "`n"
    if ($models -match [regex]::Escape($OllamaModel)) {
        Write-Ok "Model present: $OllamaModel"
    } else {
        Write-Warn "Model not found; downloading: $OllamaModel (large file, may take a while)..."
        & ollama pull $OllamaModel
        if ($LASTEXITCODE -eq 0) {
            Write-Ok "Model downloaded: $OllamaModel"
        } else {
            Write-Warn "Model download failed (exit $LASTEXITCODE). Try manually: ollama pull $OllamaModel"
        }
    }
}

# ════════════════════════════════════════════════════════════════
# 4. Database init
# ════════════════════════════════════════════════════════════════
function Initialize-Database {
    Write-Step 4 $TotalSteps "Creating database tables..."
    & $VenvPython "init_db.py"
    if ($LASTEXITCODE -ne 0) {
        Write-Err "Database initialization failed! (init_db.py exit $LASTEXITCODE)"
        exit 1
    }
    Write-Ok
}

# ════════════════════════════════════════════════════════════════
# 5. FastAPI
# ════════════════════════════════════════════════════════════════
function Start-Api {
    Write-Step 5 $TotalSteps "Starting FastAPI server..."
    $env:PYTHONIOENCODING = "utf-8"
    $env:PYTHONUNBUFFERED = "1"

    $proc = Start-Process -FilePath $VenvPython `
        -ArgumentList "-m", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--log-level", "info" `
        -WorkingDirectory $ProjectDir `
        -NoNewWindow -PassThru
    $script:OwnedProcs += $proc
    Write-Ok "(PID: $($proc.Id))"
}

# ════════════════════════════════════════════════════════════════
# 6. Next.js dashboard
# ════════════════════════════════════════════════════════════════
function Start-Dashboard {
    Write-Step 6 $TotalSteps "Starting Next.js dashboard..."

    $npm = (Get-Command npm.cmd -ErrorAction SilentlyContinue)
    if (-not $npm) { $npm = (Get-Command npm -ErrorAction SilentlyContinue) }
    if (-not $npm) {
        Write-Err "npm not found. Is Node.js installed?"
        Stop-OwnedProcs
        exit 1
    }

    $proc = Start-Process -FilePath $npm.Source `
        -ArgumentList "run", "dev" `
        -WorkingDirectory $DashboardDir `
        -NoNewWindow -PassThru
    $script:OwnedProcs += $proc
    Write-Ok "(PID: $($proc.Id))"
}

# ════════════════════════════════════════════════════════════════
# 7. Wait for readiness
# ════════════════════════════════════════════════════════════════
function Wait-Servers {
    Write-Step 7 $TotalSteps "Waiting for servers to become ready..."
    $apiReady = $false
    $dashReady = $false
    $deadline = (Get-Date).AddSeconds($StartupTimeout)

    while ((Get-Date) -lt $deadline) {
        if (-not $apiReady)  { $apiReady  = Test-HttpOk -Url $ApiUrl }
        if (-not $dashReady) { $dashReady = Test-HttpOk -Url $DashboardUrl }
        if ($apiReady -and $dashReady) { Write-Ok; return }

        foreach ($p in $script:OwnedProcs) {
            if ($null -ne $p -and $p.HasExited) {
                Write-Err "A process crashed (PID $($p.Id), exit $($p.ExitCode)). See the output above."
                Stop-OwnedProcs
                exit 1
            }
        }
        Start-Sleep -Milliseconds 800
    }

    Write-Err "Servers did not respond within ${StartupTimeout}s. See the output above."
    Stop-OwnedProcs
    exit 1
}

# ════════════════════════════════════════════════════════════════
# Keep alive
# ════════════════════════════════════════════════════════════════
function Invoke-ServeForever {
    $url = "http://localhost:3000/"
    try { Start-Process $url | Out-Null } catch {}

    Write-Host ""
    Write-Host "  ─────────────────────────────────────────" -ForegroundColor DarkGray
    Write-Host "  Dashboard: $url" -ForegroundColor Green
    Write-Host "  API Docs : http://localhost:8000/docs" -ForegroundColor Green
    Write-Host "  Logs stream below. Press Ctrl+C to stop." -ForegroundColor DarkGray
    Write-Host "  ─────────────────────────────────────────" -ForegroundColor DarkGray
    Write-Host ""

    try {
        while ($true) { Start-Sleep -Seconds 1 }
    } finally {
        # Runs on Ctrl+C (PipelineStoppedException) and normal exit alike.
        Stop-OwnedProcs
    }
}

# ── Main ───────────────────────────────────────────────────────
Set-Location $ProjectDir
Write-Banner
Invoke-PreChecks
Start-Postgres
Start-Ollama
Initialize-Database
Start-Api
Start-Dashboard
Wait-Servers
Invoke-ServeForever
