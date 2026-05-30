# 巡查者 — All-in-One Build Script
# Builds Backend, Commander, and Agent for deployment

param(
    [switch]$Backend,     # Build Backend only
    [switch]$Commander,   # Build Commander only
    [switch]$Agent,       # Build Agent only
    [switch]$Help         # Show help
)

$ROOT = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$LOGDIR = "$ROOT\logs"

function Write-Status {
    param([string]$Label, [string]$Status, [string]$Color = "White")
    $timestamp = Get-Date -Format "HH:mm:ss"
    Write-Host "[$timestamp] " -NoNewline
    Write-Host "$Label " -NoNewline -ForegroundColor Cyan
    Write-Host $Status -ForegroundColor $Color
}

# ── Help ───────────────────────────────────────────────────────────
if ($Help) {
    Write-Status "HELP" "巡查者 Build Script" "Cyan"
    Write-Host ""
    Write-Host "Usage: .\build-all.ps1 [options]"
    Write-Host ""
    Write-Host "Options:"
    Write-Host "  -Backend     Build only the Backend (TypeScript -> dist/)"
    Write-Host "  -Commander   Build only the Commander (Vite + Electron TS)"
    Write-Host "  -Agent       Build only the Agent (PyInstaller .exe)"
    Write-Host "  -Help        Show this help"
    Write-Host ""
    Write-Host "Default (no flags): Build all three components"
    Write-Host ""
    Write-Host "Examples:"
    Write-Host "  .\build-all.ps1                # Build everything"
    Write-Host "  .\build-all.ps1 -Backend       # Backend only"
    Write-Host "  .\build-all.ps1 -B -C          # Backend + Commander"
    exit 0
}

# Determine target scope
$buildAll = (-not $Backend -and -not $Commander -and -not $Agent)
$buildBackend = $buildAll -or $Backend
$buildCommander = $buildAll -or $Commander
$buildAgent = $buildAll -or $Agent

# ── Pre-flight ─────────────────────────────────────────────────────
Write-Status "Pre-flight" "Checking prerequisites..." "White"

$hasNode = Get-Command "node" -ErrorAction SilentlyContinue
if (-not $hasNode) {
    Write-Status "ERROR" "Node.js not found in PATH. Install from https://nodejs.org" "Red"
    exit 1
}

# Ensure log directory exists
if (-not (Test-Path $LOGDIR)) {
    New-Item -ItemType Directory -Path $LOGDIR -Force | Out-Null
}

Write-Status "Pre-flight" "All prerequisites OK" "Green"

$buildPassed = 0
$buildFailed = 0
$buildSkipped = 0

# ── Build Backend ──────────────────────────────────────────────────
if ($buildBackend) {
    Write-Status "Backend" "Building TypeScript..." "White"

    if (-not (Test-Path "$ROOT\backend\node_modules")) {
        Write-Status "Backend" "Installing dependencies..." "Yellow"
        Push-Location "$ROOT\backend"
        npm install 2>&1 | Out-Null
        Pop-Location
    }

    Push-Location "$ROOT\backend"
    $output = npm run build 2>&1
    $exitCode = $LASTEXITCODE
    Pop-Location

    $output | Out-File "$LOGDIR\backend-build.log"

    if ($exitCode -eq 0) {
        Write-Status "Backend" "Build SUCCESS => $ROOT\backend\dist\" "Green"
        $buildPassed++
    } else {
        Write-Status "Backend" "Build FAILED (exit code: $exitCode)" "Red"
        Write-Status "Backend" "See $LOGDIR\backend-build.log" "Yellow"
        $buildFailed++
    }
}

# ── Build Commander ────────────────────────────────────────────────
if ($buildCommander) {
    Write-Status "Commander" "Building Vite + Electron..." "White"

    if (-not (Test-Path "$ROOT\commander\node_modules")) {
        Write-Status "Commander" "Installing dependencies..." "Yellow"
        Push-Location "$ROOT\commander"
        npm install 2>&1 | Out-Null
        Pop-Location
    }

    Push-Location "$ROOT\commander"
    $output = npm run build 2>&1
    $exitCode = $LASTEXITCODE
    Pop-Location

    $output | Out-File "$LOGDIR\commander-build.log"

    if ($exitCode -eq 0) {
        Write-Status "Commander" "Build SUCCESS => $ROOT\commander\dist\" "Green"
        $buildPassed++
    } else {
        Write-Status "Commander" "Build FAILED (exit code: $exitCode)" "Red"
        Write-Status "Commander" "See $LOGDIR\commander-build.log" "Yellow"
        $buildFailed++
    }
}

# ── Build Agent ────────────────────────────────────────────────────
if ($buildAgent) {
    Write-Status "Agent" "Checking build script..." "White"

    $agentBuildScript = "$ROOT\scripts\build-agent.ps1"

    if (Test-Path $agentBuildScript) {
        Write-Status "Agent" "Running build-agent.ps1..." "White"

        & $agentBuildScript 2>&1 | Tee-Object -FilePath "$LOGDIR\agent-build.log"
        $exitCode = $LASTEXITCODE

        if ($exitCode -eq 0) {
            Write-Status "Agent" "Build SUCCESS => $ROOT\agent\dist\" "Green"
            $buildPassed++
        } else {
            Write-Status "Agent" "Build FAILED (exit code: $exitCode)" "Red"
            Write-Status "Agent" "See $LOGDIR\agent-build.log" "Yellow"
            $buildFailed++
        }
    } else {
        Write-Status "Agent" "SKIPPED — build-agent.ps1 not found" "Yellow"
        Write-Status "Agent" "Create $agentBuildScript to enable Agent builds" "Yellow"
        $buildSkipped++
    }
}

# ── Summary ────────────────────────────────────────────────────────
$total = $buildPassed + $buildFailed + $buildSkipped
$summaryColor = if ($buildFailed -gt 0) { "Yellow" } else { "Green" }

Write-Status "====" "==============================" "White"
Write-Status "DONE" "Build complete ($buildPassed passed, $buildFailed failed, $buildSkipped skipped of $total)" $summaryColor
Write-Status "    " "" "White"

if ($buildBackend -and (Test-Path "$ROOT\backend\dist")) {
    Write-Status "    " "Backend:   $ROOT\backend\dist\" "Cyan"
}
if ($buildCommander -and (Test-Path "$ROOT\commander\dist")) {
    Write-Status "    " "Commander: $ROOT\commander\dist\" "Cyan"
}
if ($buildAgent -and (Test-Path "$ROOT\agent\dist")) {
    Write-Status "    " "Agent:     $ROOT\agent\dist\" "Cyan"
}

Write-Status "    " "" "White"
Write-Status "    " "Build logs: $LOGDIR\*-build.log" "Yellow"
Write-Status "====" "==============================" "White"

if ($buildFailed -gt 0) {
    Write-Status "WARN" "Some builds failed. Review the logs above." "Yellow"
}

exit 0
