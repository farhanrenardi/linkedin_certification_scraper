# LinkedIn Certificate Scraper - Windows Installation Script
# Run: .\install.ps1 needs

param(
    [Parameter(Position=0)]
    [string]$Command
)

if ($Command -ne "needs") {
    Write-Host "Usage: .\install.ps1 needs" -ForegroundColor Yellow
    exit 1
}

Write-Host "LinkedIn Certificate Scraper - Installing dependencies..." -ForegroundColor Cyan

# Check Python
$pythonCmd = $null
if (Get-Command python -ErrorAction SilentlyContinue) {
    $pythonCmd = "python"
} elseif (Get-Command python3 -ErrorAction SilentlyContinue) {
    $pythonCmd = "python3"
} else {
    Write-Host "Error: Python not found. Please install Python 3.10 or higher." -ForegroundColor Red
    exit 1
}

# Check Python version
$version = & $pythonCmd --version 2>&1
Write-Host "Found: $version" -ForegroundColor Green

# Create virtual environment if not exists
if (-not (Test-Path ".\venv")) {
    Write-Host "Creating virtual environment..." -ForegroundColor Yellow
    & $pythonCmd -m venv venv
}

# Activate and install
$venvPython = ".\venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Host "Error: Failed to create virtual environment." -ForegroundColor Red
    exit 1
}

Write-Host "Upgrading pip..." -ForegroundColor Yellow
& $venvPython -m pip install --upgrade pip --quiet

Write-Host "Installing dependencies..." -ForegroundColor Yellow
& $venvPython -m pip install -r requirements.txt --quiet

Write-Host "Installing Playwright browsers..." -ForegroundColor Yellow
& $venvPython -m playwright install chromium

Write-Host ""
Write-Host "Installation complete!" -ForegroundColor Green
Write-Host "Run the application with: .\run.ps1 application" -ForegroundColor Cyan
