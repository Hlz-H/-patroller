# 巡查者 — Agent Build Script
# Builds the Python agent into a standalone executable via PyInstaller

param(
    [switch]$Help
)

$ROOT = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$AGENT_DIR = "$ROOT\agent"

function Write-Status {
    param([string]$Label, [string]$Status, [string]$Color = "White")
    $timestamp = Get-Date -Format "HH:mm:ss"
    Write-Host "[$timestamp] " -NoNewline
    Write-Host "$Label " -NoNewline -ForegroundColor Cyan
    Write-Host $Status -ForegroundColor $Color
}

if ($Help) {
    Write-Host "Usage: .\build-agent.ps1" -ForegroundColor Cyan
    Write-Host "Builds the patroller-agent into a standalone executable."
    exit 0
}

# Check Python
$hasPython = Get-Command "python" -ErrorAction SilentlyContinue
if (-not $hasPython) {
    Write-Status "ERROR" "Python not found in PATH" "Red"
    exit 1
}

# Check PyInstaller
$hasPyInstaller = python -m pip show pyinstaller 2>$null
if (-not $hasPyInstaller) {
    Write-Status "PyInstaller" "Not found, installing..." "Yellow"
    python -m pip install pyinstaller
    if ($LASTEXITCODE -ne 0) {
        Write-Status "ERROR" "Failed to install PyInstaller" "Red"
        exit 1
    }
    Write-Status "PyInstaller" "Installed" "Green"
}

# Check spec file
$SPEC = "$AGENT_DIR\patroller-agent.spec"
if (-not (Test-Path $SPEC)) {
    Write-Status "ERROR" "Spec file not found: $SPEC" "Red"
    Write-Status "    " "Run from project root directory" "Yellow"
    exit 1
}

# Build
Write-Status "Agent" "Building patroller-agent..." "White"
Push-Location $AGENT_DIR
pyinstaller --clean patroller-agent.spec
$exitCode = $LASTEXITCODE
Pop-Location

if ($exitCode -eq 0) {
    Write-Status "Agent" "Build successful!" "Green"
    Write-Status "    " "Output: $AGENT_DIR\dist\patroller-agent\" "Cyan"
} else {
    Write-Status "Agent" "Build failed (exit code: $exitCode)" "Red"
    exit 1
}
