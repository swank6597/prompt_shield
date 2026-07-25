# start-backend.ps1
# One-click launcher for the PromptShield backend API.
# Run from the repo root: .\start-backend.ps1
#
# What it does:
#   1. Sets execution policy (current user only, safe)
#   2. Enters backend/, creates venv if missing, activates it
#   3. Installs/updates pip dependencies
#   4. Starts uvicorn with live reload on port 8081
#   5. All Python logs stream directly to this console window

Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser -Force

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendDir = Join-Path $repoRoot "backend"

Write-Host ""
Write-Host "=== PromptShield Backend Launcher ===" -ForegroundColor Cyan
Write-Host ""

# --- Navigate to backend ---
Set-Location $backendDir
Write-Host "[1/4] Working directory: $backendDir" -ForegroundColor Green

# --- Create venv if it doesn't exist ---
if (-Not (Test-Path "venv")) {
    Write-Host "[2/4] Creating virtual environment..." -ForegroundColor Yellow
    python -m venv venv
} else {
    Write-Host "[2/4] Virtual environment already exists" -ForegroundColor Green
}

# --- Activate venv ---
Write-Host "[3/4] Activating venv and installing dependencies..." -ForegroundColor Yellow
& ".\venv\Scripts\Activate.ps1"

# Install/update dependencies (quiet mode to reduce noise)
pip install -r requirements.txt -q

# --- Start the server ---
Write-Host "[4/4] Starting uvicorn on http://localhost:8081 ..." -ForegroundColor Green
Write-Host ""
Write-Host "Press Ctrl+C to stop the server." -ForegroundColor DarkGray
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Set log level to DEBUG for detailed LLM response logging
$env:PROMPTSHIELD_LOG_LEVEL = "DEBUG"

# Run uvicorn - logs stream directly to this console
uvicorn app:app --reload --port 8081 --log-level info
