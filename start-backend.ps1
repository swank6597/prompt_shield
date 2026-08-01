# start-backend.ps1
# One-click launcher for the PromptShield backend API.
# Run from the repo root: .\start-backend.ps1
#
# What it does:
#   1. Sets execution policy (current user only, safe)
#   2. Enters backend/, creates venv if missing, activates it
#   3. Installs/updates pip dependencies
#   4. Ensures backend/.env exists and has PROMPTSHIELD_AUTH_SECRET_KEY set -
#      backend/auth/security.py raises RuntimeError at import time without
#      it, so uvicorn would otherwise fail to start
#   5. Starts uvicorn with live reload on port 8081
#   6. All Python logs stream directly to this console window

Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser -Force

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendDir = Join-Path $repoRoot "backend"

Write-Host ""
Write-Host "=== PromptShield Backend Launcher ===" -ForegroundColor Cyan
Write-Host ""

# --- Navigate to backend ---
Set-Location $backendDir
Write-Host "[1/6] Working directory: $backendDir" -ForegroundColor Green

# --- Create venv if it doesn't exist ---
if (-Not (Test-Path "venv")) {
    Write-Host "[2/6] Creating virtual environment..." -ForegroundColor Yellow
    python -m venv venv
} else {
    Write-Host "[2/6] Virtual environment already exists" -ForegroundColor Green
}

# --- Activate venv ---
Write-Host "[3/6] Activating venv and installing dependencies..." -ForegroundColor Yellow
& ".\venv\Scripts\Activate.ps1"

# Install/update dependencies (quiet mode to reduce noise)
pip install -r requirements.txt -q

# --- Ensure backend/.env exists and has a real PROMPTSHIELD_AUTH_SECRET_KEY ---
# Never overwrites an already-set key: rotating it invalidates every existing
# JWT session instantly (see backend/auth/security.py), so this only fills in
# a missing/empty value, it doesn't "refresh" one that's already there.
Write-Host "[4/6] Checking PROMPTSHIELD_AUTH_SECRET_KEY..." -ForegroundColor Yellow

$envPath = Join-Path $backendDir ".env"
$envExamplePath = Join-Path $backendDir ".env.example"

if (-Not (Test-Path $envPath)) {
    if (Test-Path $envExamplePath) {
        Copy-Item $envExamplePath $envPath
        Write-Host "       Created backend\.env from .env.example" -ForegroundColor DarkGray
    } else {
        New-Item -ItemType File -Path $envPath | Out-Null
    }
}

$envContent = Get-Content $envPath -Raw -ErrorAction SilentlyContinue
if ($null -eq $envContent) { $envContent = "" }

$secretLinePattern = '(?m)^PROMPTSHIELD_AUTH_SECRET_KEY=(.*)$'
$match = [regex]::Match($envContent, $secretLinePattern)

if ($match.Success -and $match.Groups[1].Value.Trim().Length -gt 0) {
    Write-Host "       Already set - leaving it alone." -ForegroundColor Green
} else {
    Write-Host "       Missing/empty - generating one..." -ForegroundColor Yellow
    $newSecret = python -c "import secrets; print(secrets.token_urlsafe(32))"

    if ($match.Success) {
        $envContent = [regex]::Replace($envContent, $secretLinePattern, "PROMPTSHIELD_AUTH_SECRET_KEY=$newSecret")
        Set-Content -Path $envPath -Value $envContent -NoNewline -Encoding utf8
    } else {
        Add-Content -Path $envPath -Value "PROMPTSHIELD_AUTH_SECRET_KEY=$newSecret" -Encoding utf8
    }
    Write-Host "       Generated and saved to backend\.env" -ForegroundColor Green
}

# --- Start the server ---
Write-Host "[5/6] Starting uvicorn on http://localhost:8081 ..." -ForegroundColor Green
Write-Host ""
Write-Host "Press Ctrl+C to stop the server." -ForegroundColor DarkGray
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Set log level to DEBUG for detailed LLM response logging
$env:PROMPTSHIELD_LOG_LEVEL = "DEBUG"

# Run uvicorn - logs stream directly to this console
uvicorn app:app --reload --port 8081 --log-level info
