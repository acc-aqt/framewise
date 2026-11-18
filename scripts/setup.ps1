# Sets up framewise on Windows from a clone of the repo, ready for `framewise review`:
#
#   1. checks the prerequisites: uv and Node.js (warning if it is not the
#      version in frontend/.nvmrc);
#   2. installs ExifTool with winget, unless it is already installed;
#   3. builds the Review UI;
#   4. installs the backend with the portable Providers and their models.
#
# Supported: Windows x64. On macOS and Linux, run scripts/setup.sh instead.
#
# Re-running is safe. Run it again after pulling to update framewise.
#
# Usage: powershell -ExecutionPolicy Bypass -File scripts\setup.ps1 [-Help]

param([switch]$Help)

$ErrorActionPreference = 'Stop'

function Show-Help {
    foreach ($line in Get-Content $PSCommandPath) {
        if ($line -notmatch '^#') { break }
        $line -replace '^# ?', ''
    }
}

function Stop-Setup([string]$Message) {
    [Console]::Error.WriteLine("setup: $Message")
    exit 1
}

function Invoke-Native {
    $command = $args[0]
    $arguments = @($args | Select-Object -Skip 1)
    Write-Host "+ $($args -join ' ')"
    & $command @arguments
    if ($LASTEXITCODE -ne 0) {
        Stop-Setup "'$($args -join ' ')' failed with exit code $LASTEXITCODE."
    }
}

function Test-Command([string]$Name) {
    [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

function Add-RegistryPathToSession {
    $session = $env:Path -split ';' | Where-Object { $_ }
    $registry = @(
        [Environment]::GetEnvironmentVariable('Path', 'Machine')
        [Environment]::GetEnvironmentVariable('Path', 'User')
    ) -split ';' | Where-Object { $_ }
    $missing = $registry | Where-Object { $session -notcontains $_ }
    $env:Path = (@($session) + @($missing)) -join ';'
}

function Test-Prerequisites {
    if (-not (Test-Command 'uv')) {
        Stop-Setup 'uv is not installed. Install it from https://docs.astral.sh/uv/getting-started/installation/ and run this script again.'
    }

    $wanted = (Get-Content (Join-Path $RepoRoot 'frontend/.nvmrc') -Raw).Trim().TrimStart('v')
    if (-not (Test-Command 'node')) {
        Stop-Setup "Node.js is not installed. The frontend expects Node $wanted, as recorded in frontend/.nvmrc."
    }
    $actual = (node --version).Trim().TrimStart('v')
    if ($actual -ne $wanted -and -not $actual.StartsWith("$wanted.")) {
        [Console]::Error.WriteLine("setup: warning: the frontend expects Node $wanted, as recorded in frontend/.nvmrc, but found Node $actual. Switch to Node $wanted if the build fails.")
    }
}

# winget's exit code when the package is already installed and has no upgrade.
$WingetAlreadyInstalled = -1978335189

function Install-ExifTool {
    # A terminal opened before an earlier run does not see the PATH winget changed.
    Add-RegistryPathToSession
    if (Test-Command 'exiftool') {
        Write-Host 'ExifTool is already installed.'
        return
    }
    if (-not (Test-Command 'winget')) {
        Stop-Setup 'ExifTool is not installed and winget is not available to install it. Install winget (App Installer, from the Microsoft Store) or ExifTool from https://exiftool.org, then run this script again.'
    }
    Write-Host '+ winget install --id OliverBetz.ExifTool'
    winget install --id OliverBetz.ExifTool --exact --silent --accept-source-agreements --accept-package-agreements
    if ($LASTEXITCODE -ne 0 -and $LASTEXITCODE -ne $WingetAlreadyInstalled) {
        Stop-Setup "installing ExifTool with winget failed with exit code $LASTEXITCODE."
    }
    Add-RegistryPathToSession
    if (-not (Test-Command 'exiftool')) {
        Stop-Setup 'ExifTool was installed but is not on PATH yet. Open a new terminal and run this script again.'
    }
}

function Build-ReviewUi {
    Push-Location (Join-Path $RepoRoot 'frontend')
    try {
        Invoke-Native npm ci
        Invoke-Native npx ng build
    } finally {
        Pop-Location
    }
}

function Install-Backend {
    Push-Location (Join-Path $RepoRoot 'backend')
    try {
        Invoke-Native uv sync --locked --extra portable
        Invoke-Native uv run framewise models download
    } finally {
        Pop-Location
    }
}

if ($Help) {
    Show-Help
    exit 0
}

$RepoRoot = Split-Path -Parent $PSScriptRoot

Test-Prerequisites
Install-ExifTool
Build-ReviewUi
Install-Backend

Write-Host 'framewise is set up. Review a Session with: cd backend; uv run framewise review'
