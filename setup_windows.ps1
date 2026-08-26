$ErrorActionPreference = "Stop"

Write-Host "== AI Screen Assistant Windows setup ==" -ForegroundColor Cyan

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw "Python was not found on PATH. Install Python 3.11+ and run this script again."
}

if (-not (Test-Path ".\venv\Scripts\python.exe")) {
    Write-Host "Creating project virtual environment..." -ForegroundColor Yellow
    python -m venv venv
}

$Python = (Resolve-Path ".\venv\Scripts\python.exe").Path

Write-Host "Upgrading pip..." -ForegroundColor Yellow
& $Python -m pip install --upgrade pip

Write-Host "Installing Python dependencies..." -ForegroundColor Yellow
& $Python -m pip install -r requirements.txt

Write-Host "Installing Playwright Chromium browser runtime..." -ForegroundColor Yellow
& $Python -m playwright install chromium

Write-Host "Checking PyQt6..." -ForegroundColor Yellow
& $Python -c "import PyQt6; print('PyQt6 OK')"

Write-Host "Checking Playwright..." -ForegroundColor Yellow
& $Python -c "import playwright; print('Playwright OK')"

Write-Host "Setup complete." -ForegroundColor Green
Write-Host "Activate with: .\venv\Scripts\Activate.ps1" -ForegroundColor Cyan
Write-Host "Then run: python main.py" -ForegroundColor Cyan
