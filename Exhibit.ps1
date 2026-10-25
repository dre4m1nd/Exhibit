# Launch the Exhibit terminal agent.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Error "缺少 .venv，请先运行: python -m venv .venv; .\.venv\Scripts\pip install -r requirements.txt"
}

if (-not (Test-Path "tui\node_modules")) {
    Write-Error "缺少 tui/node_modules，请先运行: cd tui; npm install"
}

if (-not (Test-Path "tui\dist\main.js")) {
    Write-Host "首次运行，正在编译 TUI..." -ForegroundColor Yellow
    Push-Location tui
    node node_modules\typescript\bin\tsc -p tsconfig.json
    Pop-Location
}

node tui\dist\main.js
