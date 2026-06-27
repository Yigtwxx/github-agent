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
      5. FastAPI     - background process on :8000 (logs/server.log)
      6. Next.js     - background dev server on :3000 (logs/dashboard.log)
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
$LogDir       = Join-Path $ProjectDir "logs"
$ServerLog    = Join-Path $LogDir "server.log"
$DashboardLog = Join-Path $LogDir "dashboard.log"
$OllamaLog    = Join-Path $LogDir "ollama.log"

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
    Write-Host "  ║          🤖 GitHub AI Agent - Başlatıcı          ║" -ForegroundColor Cyan
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

function Get-LogTail {
    param([string]$Path, [int]$Lines = 20)
    if (Test-Path $Path) {
        return (Get-Content -Path $Path -Tail $Lines -ErrorAction SilentlyContinue) -join "`n"
    }
    return ""
}

function Stop-OwnedProcs {
    Write-Host ""
    Write-Host "  🛑 Sunucular kapatılıyor..." -ForegroundColor DarkGray
    foreach ($p in $script:OwnedProcs) {
        if ($null -ne $p -and -not $p.HasExited) {
            # taskkill /T kills the whole child tree (npm -> next-dev node children).
            & taskkill /F /T /PID $p.Id 2>$null | Out-Null
        }
    }
    Write-Host "  👋 Görüşmek üzere!" -ForegroundColor Green
    Write-Host ""
}

# ════════════════════════════════════════════════════════════════
# 1. Pre-flight checks
# ════════════════════════════════════════════════════════════════
function Invoke-PreChecks {
    Write-Step 1 $TotalSteps "Ön kontroller yapılıyor..."
    $errors = @()

    $envPath = Join-Path $ProjectDir ".env"
    if (-not (Test-Path $envPath)) {
        $errors += ".env dosyası bulunamadı! .env.example dosyasını kopyalayın."
    } else {
        $tokenLine = Select-String -Path $envPath -Pattern '^\s*GITHUB_TOKEN\s*=\s*(.+)$' -ErrorAction SilentlyContinue
        $tokenVal = if ($tokenLine) { $tokenLine.Matches[0].Groups[1].Value.Trim() } else { "" }
        if (-not $tokenVal -or $tokenVal -eq "ghp_YOUR_TOKEN_HERE") {
            $errors += "GITHUB_TOKEN ayarlanmamış! .env dosyasını düzenleyin."
        }
    }

    if (-not (Test-Path $VenvPython)) {
        $errors += "Virtual environment bulunamadı (venv\Scripts\python.exe). 'python -m venv venv' çalıştırın."
    }

    if ($errors.Count -gt 0) {
        Write-Err "Ön kontroller başarısız!"
        foreach ($e in $errors) { Write-Host "      • $e" -ForegroundColor Red }
        exit 1
    }
    Write-Ok
}

# ════════════════════════════════════════════════════════════════
# 2. PostgreSQL (local Windows service)
# ════════════════════════════════════════════════════════════════
function Start-Postgres {
    Write-Step 2 $TotalSteps "PostgreSQL başlatılıyor..."

    if (Test-Port -Port $PostgresPort) {
        Write-Ok "Zaten çalışıyor (port $PostgresPort)."
        return
    }

    $svc = Get-Service -Name 'postgresql*' -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $svc) {
        Write-Warn "PostgreSQL Windows servisi bulunamadı. DB'yi elle başlatın (port $PostgresPort)."
        return
    }

    if ($svc.Status -ne 'Running') {
        try {
            Start-Service -Name $svc.Name -ErrorAction Stop
        } catch {
            Write-Warn "Servis başlatılamadı ($($svc.Name)). Yönetici izni gerekebilir: $($_.Exception.Message)"
            return
        }
    }

    if (Wait-Port -Port $PostgresPort -TimeoutSec 30 -Label "PostgreSQL") {
        Write-Ok "$($svc.Name) çalışıyor (port $PostgresPort)."
    } else {
        Write-Warn "PostgreSQL servisi başladı ama port $PostgresPort yanıt vermedi."
    }
}

# ════════════════════════════════════════════════════════════════
# 3. Ollama (serve + auto-pull)
# ════════════════════════════════════════════════════════════════
function Start-Ollama {
    Write-Step 3 $TotalSteps "Ollama hazırlanıyor ($OllamaModel)..."

    $ollama = Get-Command ollama -ErrorAction SilentlyContinue
    if (-not $ollama) {
        Write-Warn "'ollama' komutu PATH'te yok. https://ollama.com/download adresinden kurun."
        return
    }

    # Ensure the server is up.
    if (-not (Test-Port -Port $OllamaPort)) {
        New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
        Start-Process -FilePath "ollama" -ArgumentList "serve" `
            -RedirectStandardOutput $OllamaLog -RedirectStandardError "$OllamaLog.err" `
            -WindowStyle Hidden | Out-Null
        if (Wait-Port -Port $OllamaPort -TimeoutSec 30 -Label "Ollama") {
            Write-Ok "ollama serve başlatıldı (port $OllamaPort)."
        } else {
            Write-Warn "ollama serve başlatıldı ama port $OllamaPort yanıt vermedi."
            return
        }
    } else {
        Write-Ok "Ollama zaten çalışıyor (port $OllamaPort)."
    }

    # Ensure the model is present.
    $models = (& ollama list 2>$null) -join "`n"
    if ($models -match [regex]::Escape($OllamaModel)) {
        Write-Ok "Model mevcut: $OllamaModel"
    } else {
        Write-Warn "Model bulunamadı; indiriliyor: $OllamaModel (büyük dosya, sürebilir)..."
        & ollama pull $OllamaModel
        if ($LASTEXITCODE -eq 0) {
            Write-Ok "Model indirildi: $OllamaModel"
        } else {
            Write-Warn "Model indirilemedi (exit $LASTEXITCODE). Elle deneyin: ollama pull $OllamaModel"
        }
    }
}

# ════════════════════════════════════════════════════════════════
# 4. Database init
# ════════════════════════════════════════════════════════════════
function Initialize-Database {
    Write-Step 4 $TotalSteps "Veritabanı tabloları oluşturuluyor..."
    & $VenvPython "init_db.py"
    if ($LASTEXITCODE -ne 0) {
        Write-Err "Veritabanı başlatılamadı! (init_db.py exit $LASTEXITCODE)"
        exit 1
    }
    Write-Ok
}

# ════════════════════════════════════════════════════════════════
# 5. FastAPI
# ════════════════════════════════════════════════════════════════
function Start-Api {
    Write-Step 5 $TotalSteps "FastAPI sunucusu başlatılıyor..."
    New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
    $env:PYTHONIOENCODING = "utf-8"

    $proc = Start-Process -FilePath $VenvPython `
        -ArgumentList "-m", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--log-level", "info" `
        -WorkingDirectory $ProjectDir `
        -RedirectStandardOutput $ServerLog -RedirectStandardError "$ServerLog.err" `
        -WindowStyle Hidden -PassThru
    $script:OwnedProcs += $proc
    Write-Ok "(PID: $($proc.Id))"
}

# ════════════════════════════════════════════════════════════════
# 6. Next.js dashboard
# ════════════════════════════════════════════════════════════════
function Start-Dashboard {
    Write-Step 6 $TotalSteps "Next.js Dashboard başlatılıyor..."
    New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

    $npm = (Get-Command npm.cmd -ErrorAction SilentlyContinue)
    if (-not $npm) { $npm = (Get-Command npm -ErrorAction SilentlyContinue) }
    if (-not $npm) {
        Write-Err "npm bulunamadı. Node.js kurulu mu?"
        Stop-OwnedProcs
        exit 1
    }

    $proc = Start-Process -FilePath $npm.Source `
        -ArgumentList "run", "dev" `
        -WorkingDirectory $DashboardDir `
        -RedirectStandardOutput $DashboardLog -RedirectStandardError "$DashboardLog.err" `
        -WindowStyle Hidden -PassThru
    $script:OwnedProcs += $proc
    Write-Ok "(PID: $($proc.Id))"
}

# ════════════════════════════════════════════════════════════════
# 7. Wait for readiness
# ════════════════════════════════════════════════════════════════
function Wait-Servers {
    Write-Step 7 $TotalSteps "Sunucuların hazır olması bekleniyor..."
    $apiReady = $false
    $dashReady = $false
    $deadline = (Get-Date).AddSeconds($StartupTimeout)

    while ((Get-Date) -lt $deadline) {
        if (-not $apiReady)  { $apiReady  = Test-HttpOk -Url $ApiUrl }
        if (-not $dashReady) { $dashReady = Test-HttpOk -Url $DashboardUrl }
        if ($apiReady -and $dashReady) { Write-Ok; return }

        foreach ($p in $script:OwnedProcs) {
            if ($null -ne $p -and $p.HasExited) {
                Write-Err "Bir süreç çöktü (PID $($p.Id), exit $($p.ExitCode))."
                Write-Host "      API logu:`n$(Get-LogTail $ServerLog)" -ForegroundColor Yellow
                Write-Host "      Dashboard logu:`n$(Get-LogTail $DashboardLog)" -ForegroundColor Yellow
                Stop-OwnedProcs
                exit 1
            }
        }
        Start-Sleep -Milliseconds 800
    }

    Write-Err "Sunucular ${StartupTimeout}s içinde yanıt vermedi."
    if (-not $apiReady)  { Write-Host "      API logu (logs/server.log):`n$(Get-LogTail $ServerLog)" -ForegroundColor Yellow }
    if (-not $dashReady) { Write-Host "      Dashboard logu (logs/dashboard.log):`n$(Get-LogTail $DashboardLog)" -ForegroundColor Yellow }
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
    Write-Host "  Loglar   : logs/server.log, logs/dashboard.log" -ForegroundColor DarkGray
    Write-Host "  Kapatmak için Ctrl+C." -ForegroundColor DarkGray
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
