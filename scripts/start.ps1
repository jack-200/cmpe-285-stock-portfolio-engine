# Stock Portfolio Engine - Windows Startup Script
# This script manages the virtual environment, installs dependencies, and starts the backend.

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path "$ScriptDir\.."
$VenvDir = "$ProjectRoot\.venv"
$ReqFile = "$ProjectRoot\requirements.txt"
$DepsStamp = "$VenvDir\.deps-installed"

# 1. Handle Virtual Environment
$NeedInstall = $false
if (-not (Test-Path $VenvDir)) {
    Write-Host "Creating virtual environment in .venv..." -ForegroundColor Yellow
    python -m venv $VenvDir
    $NeedInstall = $true
} elseif (-not (Test-Path $DepsStamp) -or (Get-Item $ReqFile).LastWriteTime -gt (Get-Item $DepsStamp).LastWriteTime) {
    $NeedInstall = $true
}

# 2. Install Dependencies
if ($NeedInstall) {
    Write-Host "Installing/Updating dependencies from requirements.txt..." -ForegroundColor Yellow
    & "$VenvDir\Scripts\pip.exe" install --upgrade pip
    & "$VenvDir\Scripts\pip.exe" install -r $ReqFile
    New-Item -Path $DepsStamp -ItemType File -Force | Out-Null
}

# 3. Load .env
$EnvFile = "$ProjectRoot\.env"
if (Test-Path $EnvFile) {
    Get-Content $EnvFile | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith("#")) {
            if ($line -match '^([^=]+)=(.*)$') {
                $key = $matches[1].Trim()
                $value = $matches[2].Trim()
                Set-Item "Env:$key" $value
            }
        }
    }
}

# 4. Start Application
Write-Host "Starting InvestIQ..." -ForegroundColor Cyan
Write-Host "Project Root: $ProjectRoot" -ForegroundColor Gray
Write-Host "LLM Backend:  $env:LLM_BACKEND"
Write-Host "LLM Model:    $env:LLM_MODEL"
Write-Host ""

& "$VenvDir\Scripts\python.exe" "$ProjectRoot\main.py"
