# LinkedIn Certificate Scraper - Windows Stop Script
# Run: .\stop.ps1

Write-Host "Stopping LinkedIn Certificate Scraper..." -ForegroundColor Yellow

# Stop UI process
if (Test-Path ".\.run_ui.pid") {
    $pid = Get-Content ".\.run_ui.pid"
    $process = Get-Process -Id $pid -ErrorAction SilentlyContinue
    if ($process) {
        Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
        Write-Host "Stopped UI process (PID $pid)" -ForegroundColor Green
    }
    Remove-Item ".\.run_ui.pid" -ErrorAction SilentlyContinue
}

# Stop CDP Chrome process
if (Test-Path ".\.cdp.pid") {
    $pid = Get-Content ".\.cdp.pid"
    $process = Get-Process -Id $pid -ErrorAction SilentlyContinue
    if ($process) {
        Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
        Write-Host "Stopped CDP Chrome (PID $pid)" -ForegroundColor Green
    }
    Remove-Item ".\.cdp.pid" -ErrorAction SilentlyContinue
}

# Remove profile marker
Remove-Item ".\.cdp.profile" -ErrorAction SilentlyContinue

# Kill any remaining Chrome CDP processes
$cdpProcesses = Get-Process -Name "chrome" -ErrorAction SilentlyContinue | Where-Object {
    $_.CommandLine -like "*remote-debugging-port=9222*"
}
if ($cdpProcesses) {
    $cdpProcesses | Stop-Process -Force -ErrorAction SilentlyContinue
}

# Kill any remaining Python uvicorn processes for this app
$uvicornProcesses = Get-Process -Name "python*" -ErrorAction SilentlyContinue | Where-Object {
    $_.CommandLine -like "*run_ui.py*" -or $_.CommandLine -like "*uvicorn*ui_app*"
}
if ($uvicornProcesses) {
    $uvicornProcesses | Stop-Process -Force -ErrorAction SilentlyContinue
}

Write-Host ""
Write-Host "Stopped UI and CDP (if running)." -ForegroundColor Green
