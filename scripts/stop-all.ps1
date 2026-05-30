# 巡查者 — All-in-One Stop Script
# Stops all running Patroller services (jobs and processes)

param(
    [switch]$Force,   # Force-kill processes on known ports regardless of job status
    [switch]$Help     # Show help
)

$ROOT = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$LOGDIR = "$ROOT\logs"
$RUNNING_FILE = "$LOGDIR\.running.json"

function Write-Status {
    param([string]$Label, [string]$Status, [string]$Color = "White")
    $timestamp = Get-Date -Format "HH:mm:ss"
    Write-Host "[$timestamp] " -NoNewline
    Write-Host "$Label " -NoNewline -ForegroundColor Cyan
    Write-Host $Status -ForegroundColor $Color
}

# ── Help ───────────────────────────────────────────────────────────
if ($Help) {
    Write-Status "HELP" "巡查者 Stop Script" "Cyan"
    Write-Host ""
    Write-Host "Usage: .\stop-all.ps1 [options]"
    Write-Host ""
    Write-Host "Options:"
    Write-Host "  -Force   Force-kill all processes on known ports (3099, 8099, 5173)"
    Write-Host "           even if no managed jobs are found"
    Write-Host "  -Help    Show this help"
    Write-Host ""
    Write-Host "Default: Stop known Patroller jobs gracefully, then kill port processes"
    Write-Host "         if any remain. With -Force, skip job lookup and kill processes directly."
    Write-Host ""
    Write-Host "Examples:"
    Write-Host "  .\stop-all.ps1          # Graceful stop via jobs"
    Write-Host "  .\stop-all.ps1 -Force   # Aggressive process kill"
    exit 0
}

$stopped = 0
$notFound = 0

# ── Kill Processes on Known Ports ──────────────────────────────────
function Stop-Port {
    param([int]$Port, [string]$Name)

    $conns = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
    if (-not $conns) {
        Write-Status "$Name" "No process on port $Port" "Yellow"
        $script:notFound++
        return
    }

    foreach ($conn in $conns) {
        $pid = $conn.OwningProcess
        try {
            $proc = Get-Process -Id $pid -ErrorAction Stop
            Write-Status "$Name" "Stopping process $($proc.ProcessName) (PID $pid) on port $Port..." "White"
            Stop-Process -Id $pid -Force
            Write-Status "$Name" "Stopped (port $Port freed)" "Green"
            $script:stopped++
        } catch {
            Write-Status "$Name" "Process PID $pid already gone" "Yellow"
        }
    }
}

# ── Stop via Job Names (from start-all.ps1) ────────────────────────
Write-Status "INFO" "Scanning for managed jobs..." "White"

$jobNames = @("patroller-backend", "patroller-agent", "patroller-commander")
$jobsFound = @()

foreach ($name in $jobNames) {
    $job = Get-Job -Name $name -ErrorAction SilentlyContinue
    if ($job) {
        $jobsFound += $job
    }
}

# ── Stop via .running.json (from start-all.ps1) ───────────────────
$runningJobs = @()
if (Test-Path $RUNNING_FILE) {
    Write-Status "INFO" "Found $RUNNING_FILE — checking tracked jobs..." "White"
    try {
        $runningData = Get-Content $RUNNING_FILE -Raw | ConvertFrom-Json
        $trackedIds = @(
            $runningData.Backend,
            $runningData.Agent,
            $runningData.Commander
        ) | Where-Object { $_ -ne $null }

        foreach ($id in $trackedIds) {
            $job = Get-Job -Id $id -ErrorAction SilentlyContinue
            if ($job) {
                $runningJobs += $job
            }
        }
    } catch {
        Write-Status "WARN" "Failed to parse $RUNNING_FILE — skipping tracked jobs" "Yellow"
    }
} else {
    Write-Status "INFO" "No $RUNNING_FILE found (services may not be running via start-all.ps1)" "Yellow"
}

# Union of jobs found by name and by .running.json
$allJobs = @($jobsFound) + @($runningJobs) | Select-Object -Unique

if (-not $Force) {
    # ── Graceful Stop ──────────────────────────────────────────────
    if ($allJobs.Count -gt 0) {
        Write-Status "INFO" "Stopping $($allJobs.Count) managed job(s) gracefully..." "White"
        $allJobs | ForEach-Object {
            $jobName = $_.Name
            try {
                Stop-Job -Job $_ -ErrorAction Stop
                Write-Status "$jobName" "Job stopped" "Green"
                $stopped++
            } catch {
                Write-Status "$jobName" "Failed to stop job: $_" "Red"
            }
            try {
                Remove-Job -Job $_ -ErrorAction Stop
            } catch {
                Write-Status "$jobName" "Job already removed" "Yellow"
            }
        }
    } else {
        Write-Status "INFO" "No managed Patroller jobs found" "Yellow"
    }

    # Clean up .running.json
    if (Test-Path $RUNNING_FILE) {
        Remove-Item -Path $RUNNING_FILE -Force
        Write-Status "INFO" "Removed $RUNNING_FILE" "Green"
    }
}

# ── Kill Port Processes ────────────────────────────────────────────
Write-Status "INFO" "Checking for processes on known ports..." "White"

$ports = @(
    @{Port = 3099; Name = "Backend"}
    @{Port = 8099; Name = "Agent"  }
    @{Port = 5173; Name = "Commander"}
)

foreach ($entry in $ports) {
    Stop-Port -Port $entry.Port -Name $entry.Name
}

# ── Summary ────────────────────────────────────────────────────────
$total = $stopped + $notFound
Write-Status "====" "==============================" "White"
Write-Status "DONE" "Stopped $stopped processes, $notFound ports already free ($total total)" "Green"
Write-Status "====" "==============================" "White"

exit 0
