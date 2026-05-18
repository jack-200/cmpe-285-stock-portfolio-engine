param(
    [switch]$PullOnly
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path (Join-Path $ScriptDir '..')
Set-Location $ProjectRoot

function Import-DotEnv {
    param(
        [string]$Path
    )

    if (-not (Test-Path $Path)) {
        return
    }

    Get-Content $Path | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith('#')) {
            return
        }

        if ($line -match '^([^=]+)=(.*)$') {
            $key = $matches[1].Trim()
            $value = $matches[2].Trim()
            Set-Item "Env:$key" $value
        }
    }
}

function Get-OllamaExecutable {
    $command = Get-Command ollama -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

    $candidatePaths = @()

    if ($env:LOCALAPPDATA) {
        $candidatePaths += (Join-Path $env:LOCALAPPDATA 'Programs\Ollama\ollama.exe')
    }

    if ($env:ProgramFiles) {
        $candidatePaths += (Join-Path $env:ProgramFiles 'Ollama\ollama.exe')
    }

    if (${env:ProgramFiles(x86)}) {
        $candidatePaths += (Join-Path ${env:ProgramFiles(x86)} 'Ollama\ollama.exe')
    }

    foreach ($candidate in $candidatePaths) {
        if ($candidate -and (Test-Path $candidate)) {
            return $candidate
        }
    }

    return $null
}

function Install-Ollama {
    Write-Host 'Installing Ollama via the official Windows installer...' -ForegroundColor Yellow
    Invoke-RestMethod -Uri 'https://ollama.com/install.ps1' | Invoke-Expression
}

Import-DotEnv -Path (Join-Path $ProjectRoot '.env')

$Model = if ($env:LLM_MODEL) { $env:LLM_MODEL } else { 'llama3.2' }
$OllamaExe = Get-OllamaExecutable

if (-not $PullOnly) {
    if ($OllamaExe) {
        Write-Host "Ollama found: $OllamaExe" -ForegroundColor Green
    } else {
        Install-Ollama
        $OllamaExe = Get-OllamaExecutable
    }
}

if (-not $OllamaExe) {
    throw 'ollama.exe was not found. Install Ollama from https://ollama.com/download/windows, then rerun this script.'
}

Write-Host "Pulling model '$Model'..." -ForegroundColor Cyan
& $OllamaExe pull $Model

if ($LASTEXITCODE -ne 0) {
    throw "ollama pull failed with exit code $LASTEXITCODE."
}

Write-Host 'Done. Start the app with .\scripts\start.ps1' -ForegroundColor Green
