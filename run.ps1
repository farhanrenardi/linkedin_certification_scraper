# LinkedIn Certificate Scraper - Windows Run Script
# Run: .\run.ps1 application

param(
    [Parameter(Position=0)]
    [string]$Command
)

if ($Command -ne "application") {
    Write-Host "Usage: .\run.ps1 application" -ForegroundColor Yellow
    exit 1
}

# Check if already running
if (Test-Path ".\.run_ui.pid") {
    $pid = Get-Content ".\.run_ui.pid"
    $process = Get-Process -Id $pid -ErrorAction SilentlyContinue
    if ($process) {
        Write-Host "UI is already running (PID $pid)." -ForegroundColor Yellow
        Write-Host "Open http://127.0.0.1:8787 in your browser." -ForegroundColor Cyan
        exit 0
    }
}

# Check venv
$venvPython = ".\venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Host "Error: Virtual environment not found. Run '.\install.ps1 needs' first." -ForegroundColor Red
    exit 1
}

Write-Host "Starting LinkedIn Certificate Scraper..." -ForegroundColor Cyan

# Start the application in background
$process = Start-Process -FilePath $venvPython -ArgumentList "run_ui.py" -PassThru -WindowStyle Hidden -RedirectStandardOutput "run_ui.log" -RedirectStandardError "run_ui_error.log"

# Save PID
$process.Id | Out-File -FilePath ".\.run_ui.pid" -NoNewline

# Wait for server to start
Start-Sleep -Seconds 3

# Check if running
if (-not $process.HasExited) {
    Write-Host ""
    Write-Host "UI started successfully!" -ForegroundColor Green
    Write-Host "Open http://127.0.0.1:8787 in your browser." -ForegroundColor Cyan
    Write-Host ""
    Write-Host "To stop: .\stop.ps1" -ForegroundColor Yellow
    
    # Try to open browser
    Start-Process "http://127.0.0.1:8787"
} else {
    Write-Host "Error: Failed to start. Check run_ui.log for details." -ForegroundColor Red
    Remove-Item ".\.run_ui.pid" -ErrorAction SilentlyContinue
    exit 1
}
