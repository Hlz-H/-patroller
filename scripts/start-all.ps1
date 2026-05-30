# 巡查者 — All-in-One Startup Script
# Starts Backend, Agent, and Commander in background

param(
    [switch]$NoCommander,   # Skip Commander startup
    [switch]$Help           # Show help
)

$ROOT = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$LOGDIR = "$ROOT\logs"

# Ensure log directory exists
if (-not (Test-Path $LOGDIR)) { New-Item -ItemType Directory -Path $LOGDIR -Force | Out-Null }

function Write-Status {
    param([string]$Label, [string]$Status, [string]$Color = "White")
    $timestamp = Get-Date -Format "HH:mm:ss"
    Write-Host "[$timestamp] " -NoNewline
    Write-Host "$Label " -NoNewline -ForegroundColor Cyan
    Write-Host $Status -ForegroundColor $Color
}

function Wait-ForPort {
    param([int]$Port, [int]$TimeoutSeconds = 30, [string]$ServiceName = "Service")
    $elapsed = 0
    while ($elapsed -lt $TimeoutSeconds) {
        $conn = Test-NetConnection -ComputerName "127.0.0.1" -Port $Port -WarningAction SilentlyIgnore -InformationLevel Quiet 2>$null
        if ($conn) { return $true }
        Start-Sleep -Seconds 2
        $elapsed += 2
        Write-Status "$ServiceName" "... waiting ($elapsed/$TimeoutSeconds s)" "Yellow"
    }
    return $false
}

# ── Check Prerequisites ──────────────────────────────────────────
Write-Status "Pre-flight" "Checking prerequisites..." "White"

$hasNode = Get-Command "node" -ErrorAction SilentlyContinue
if (-not $hasNode) { Write-Status "ERROR" "Node.js not found in PATH. Install from https://nodejs.org" "Red"; exit 1 }

$hasPython = Get-Command "python" -ErrorAction SilentlyContinue
if (-not $hasPython) { Write-Status "ERROR" "Python not found in PATH" "Red"; exit 1 }

# Check Backend node_modules
if (-not (Test-Path "$ROOT\backend\node_modules")) {
    Write-Status "Backend" "Installing dependencies..." "Yellow"
    Push-Location "$ROOT\backend"
    npm install *>&1 | Out-Null
    Pop-Location
}

# Check Commander node_modules (unless --NoCommander)
if (-not $NoCommander -and -not (Test-Path "$ROOT\commander\node_modules")) {
    Write-Status "Commander" "Installing dependencies..." "Yellow"
    Push-Location "$ROOT\commander"
    npm install *>&1 | Out-Null
    Pop-Location
}

Write-Status "Pre-flight" "All prerequisites OK" "Green"

# ── Start Backend ────────────────────────────────────────────────
Write-Status "Backend" "Starting on port 3099..." "White"
$backendJob = Start-Job -Name "patroller-backend" -ScriptBlock {
    param($dir)
    Set-Location $dir
    npm run dev 2>&1
} -ArgumentList "$ROOT\backend"

if (-not (Wait-ForPort -Port 3099 -TimeoutSeconds 15 -ServiceName "Backend")) {
    Write-Status "Backend" "FAILED to start within timeout" "Red"
    Write-Status "Backend" "Check logs at $LOGDIR\backend.log" "Yellow"
    Receive-Job -Job $backendJob -ErrorAction SilentlyContinue | Out-File "$LOGDIR\backend.log"
} else {
    Write-Status "Backend" "Ready on http://localhost:3099" "Green"
}

# ── Start Agent ──────────────────────────────────────────────────
Write-Status "Agent" "Starting on port 8099..." "White"
$agentJob = Start-Job -Name "patroller-agent" -ScriptBlock {
    param($dir)
    Set-Location $dir
    python run.py 2>&1
} -ArgumentList "$ROOT\agent"

if (-not (Wait-ForPort -Port 8099 -TimeoutSeconds 20 -ServiceName "Agent")) {
    Write-Status "Agent" "FAILED to start within timeout" "Red"
    Write-Status "Agent" "Check logs at $LOGDIR\agent.log" "Yellow"
    Receive-Job -Job $agentJob -ErrorAction SilentlyContinue | Out-File "$LOGDIR\agent.log"
} else {
    Write-Status "Agent" "Ready on http://localhost:8099" "Green"
}

# ── Start Commander (optional) ───────────────────────────────────
if (-not $NoCommander) {
    Write-Status "Commander" "Starting on port 5173..." "White"
    $commanderJob = Start-Job -Name "patroller-commander" -ScriptBlock {
        param($dir)
        Set-Location $dir
        npx vite 2>&1
    } -ArgumentList "$ROOT\commander"

    if (-not (Wait-ForPort -Port 5173 -TimeoutSeconds 30 -ServiceName "Commander")) {
        Write-Status "Commander" "FAILED to start within timeout" "Red"
        Write-Status "Commander" "Check logs at $LOGDIR\commander.log" "Yellow"
        Receive-Job -Job $commanderJob -ErrorAction SilentlyContinue | Out-File "$LOGDIR\commander.log"
    } else {
        Write-Status "Commander" "Ready on http://localhost:5173" "Green"
    }
}

# ── Summary ──────────────────────────────────────────────────────
Write-Status "====" "==============================" "White"
Write-Status "DONE" "巡查者 stack started:" "Green"
Write-Status "    " "Backend:    http://localhost:3099/api/v1/health" "Cyan"
Write-Status "    " "Agent:      http://localhost:8099/api/v1/status" "Cyan"
if (-not $NoCommander) {
    Write-Status "    " "Commander:  http://localhost:5173" "Cyan"
}
Write-Status "    " "" "White"
Write-Status "    " "Logs directory: $LOGDIR" "Yellow"
Write-Status "    " "To stop: Run scripts\stop-all.ps1 or kill the jobs manually" "Yellow"
Write-Status "====" "==============================" "White"

# Save job IDs for stop script
@{
    Backend = $backendJob.Id
    Agent = $agentJob.Id
    Commander = if ($commanderJob) { $commanderJob.Id } else { $null }
} | ConvertTo-Json | Out-File "$LOGDIR\.running.json"

# Keep script alive until user interrupts
Write-Status "INFO" "Press Ctrl+C to stop all services" "White"
try {
    while ($true) { Start-Sleep -Seconds 10 }
} finally {
    Write-Status "INFO" "Stopping all services..." "Yellow"
    Get-Job -Name "patroller-*" | Stop-Job | Remove-Job
    Write-Status "DONE" "All services stopped" "Green"
}
