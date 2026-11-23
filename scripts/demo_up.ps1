# demo_up.ps1 - one command to get a presentable stack running.
#
# Why this exists: the presentation must not depend on remembering twelve steps, on port 8080 being
# free, or on Docker Desktop already running. This script checks and fixes each of those, and prints
# exactly what to open.
#
#   powershell -ExecutionPolicy Bypass -File scripts\demo_up.ps1
#
# Options:
#   -Port 8090     host port for the app (Nginx). Default: first free port from 8090 upwards.
#   -SkipBuild     reuse existing images instead of rebuilding (faster when nothing changed)
#   -Reseed        wipe the stack's volumes and recreate the demo data (clean slate)
#   -LocalOnly     skip Docker entirely and start Django + Vite instead
#
# PowerShell 5.1 note: this script deliberately does NOT set $ErrorActionPreference='Stop'. With that
# setting, any external command that writes to stderr (docker does, constantly: pull progress, "the
# daemon is not running", ...) becomes a terminating error and aborts the run. Every native call is
# therefore checked through its exit code instead.

[CmdletBinding()]
param(
    [int]$Port = 0,
    [switch]$SkipBuild,
    [switch]$Reseed,
    [switch]$LocalOnly
)

$ErrorActionPreference = "Continue"
$repo = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $repo ".env"
$demoEmail = "manager@example.com"
$demoPassword = "Demo!Passw0rd"

function Say($message) { Write-Host "== $message" -ForegroundColor Cyan }
function Ok($message) { Write-Host "   $message" -ForegroundColor Green }
function Warn($message) { Write-Host "   $message" -ForegroundColor Yellow }

function Stop-Demo($message) {
    Write-Host ""
    Write-Host "FAILED: $message" -ForegroundColor Red
    Write-Host "Fallback: powershell -ExecutionPolicy Bypass -File scripts\demo_up.ps1 -LocalOnly" -ForegroundColor Yellow
    exit 1
}

# Run a native command and return its exit code + text output. Never throws on stderr.
#
# NOTE the named parameters: `Invoke-Native "docker" @args` would bind the first array element to
# $Exe and the rest to $args, silently dropping most of the command line — which is exactly how
# "docker compose up" turned into "docker compose".
function Invoke-Native {
    param(
        [Parameter(Mandatory = $true)][string]$Exe,
        [Parameter(Mandatory = $false)][string[]]$Arguments = @()
    )
    $output = & $Exe @Arguments 2>&1
    $code = $LASTEXITCODE
    $text = ($output | ForEach-Object { "$_" }) -join "`n"
    return [pscustomobject]@{ Code = $code; Text = $text }
}

function Test-PortFree([int]$candidate) {
    $listening = Get-NetTCPConnection -LocalPort $candidate -State Listen -ErrorAction SilentlyContinue
    return -not $listening
}

function Find-FreePort {
    foreach ($candidate in 8090..8120) { if (Test-PortFree $candidate) { return $candidate } }
    Stop-Demo "no free port between 8090 and 8120"
}

function Set-EnvValue($key, $value) {
    $lines = [System.IO.File]::ReadAllLines($envFile)
    $found = $false
    $out = foreach ($line in $lines) {
        if ($line -match "^\s*$([regex]::Escape($key))=") { $found = $true; "$key=$value" } else { $line }
    }
    if (-not $found) { $out = @($out) + "$key=$value" }
    [System.IO.File]::WriteAllText($envFile, ($out -join "`n") + "`n", (New-Object System.Text.UTF8Encoding($false)))
}

# ---------------------------------------------------------------------------
# Local-only mode: no containers at all
# ---------------------------------------------------------------------------
if ($LocalOnly) {
    Say "starting the local development servers (no Docker)"
    $python = Join-Path $repo "backend\.venv\Scripts\python.exe"
    if (-not (Test-Path $python)) { Stop-Demo "backend\.venv is missing; see docs/development/development-guide.md" }
    if (-not (Test-PortFree 8000)) { Stop-Demo "port 8000 is busy; stop whatever uses it" }
    if (-not (Test-PortFree 5173)) { Stop-Demo "port 5173 is busy; stop whatever uses it" }

    Push-Location (Join-Path $repo "backend")
    $migrate = Invoke-Native -Exe $python -Arguments @("manage.py", "migrate", "--noinput")
    if ($migrate.Code -ne 0) { Pop-Location; Stop-Demo "migrations failed: $($migrate.Text)" }
    $count = Invoke-Native -Exe $python -Arguments @("-c", "import os;os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings.development');import django;django.setup();from apps.accounts.models import User;print(User.objects.count())")
    if ($Reseed -or $count.Text.Trim() -eq "0") {
        $seed = Invoke-Native -Exe $python -Arguments @("manage.py", "seed_demo")
        if ($seed.Code -ne 0) { Pop-Location; Stop-Demo "seeding failed: $($seed.Text)" }
        Ok "demo data created"
    }
    Pop-Location

    Start-Process -FilePath $python -ArgumentList "manage.py", "runserver", "127.0.0.1:8000", "--noreload" `
        -WorkingDirectory (Join-Path $repo "backend") -WindowStyle Minimized
    Start-Process -FilePath "cmd.exe" -ArgumentList "/c", "pnpm dev" `
        -WorkingDirectory (Join-Path $repo "frontend") -WindowStyle Minimized

    Start-Sleep -Seconds 10
    Say "READY - open this in the browser"
    Ok "App      : http://localhost:5173"
    Ok "API docs : http://127.0.0.1:8000/api/docs/"
    Ok "Login    : $demoEmail / $demoPassword"
    Warn "Two windows were started (Django + Vite). Close them to stop."
    exit 0
}

# ---------------------------------------------------------------------------
# Container stack
# ---------------------------------------------------------------------------
Say "checking Docker"
$version = Invoke-Native -Exe "docker" -Arguments @("version", "--format", "{{.Server.Version}}")
if ($version.Code -ne 0) {
    $desktop = Join-Path $env:LOCALAPPDATA "Programs\DockerDesktop\Docker Desktop.exe"
    if (-not (Test-Path $desktop)) { Stop-Demo "Docker Desktop was not found" }
    Warn "the daemon is not running; starting Docker Desktop (this can take a couple of minutes)"
    Start-Process -FilePath $desktop | Out-Null
    $deadline = (Get-Date).AddSeconds(300)
    do {
        Start-Sleep -Seconds 8
        $version = Invoke-Native -Exe "docker" -Arguments @("version", "--format", "{{.Server.Version}}")
        $up = ($version.Code -eq 0)
    } while (-not $up -and (Get-Date) -lt $deadline)
    if (-not $up) { Stop-Demo "Docker did not start within 5 minutes" }
}
Ok "docker engine $($version.Text.Trim())"

Say "choosing a host port"
if ($Port -eq 0) { $Port = Find-FreePort }
elseif (-not (Test-PortFree $Port)) { Stop-Demo "port $Port is already in use" }
if (-not (Test-Path $envFile)) { Stop-Demo ".env is missing; copy .env.example to .env first" }
Set-EnvValue "NGINX_PORT" "$Port"
$s3Port = if (Test-PortFree 9090) { 9090 } else { 9091 }
Set-EnvValue "S3_PORT_HOST" "$s3Port"
Ok "app will be published on http://localhost:$Port"

Push-Location $repo
if ($Reseed) {
    Say "resetting the stack and its data (-Reseed)"
    $null = Invoke-Native -Exe "docker" -Arguments @("compose", "down", "-v", "--remove-orphans")
}

Say "building and starting the stack (the first run takes a few minutes)"
$upArgs = @("compose", "up", "-d")
if (-not $SkipBuild) { $upArgs += "--build" }
$up = Invoke-Native -Exe "docker" -Arguments $upArgs
if ($up.Code -ne 0) { Pop-Location; Stop-Demo "docker compose up failed:`n$($up.Text)" }

Say "waiting for the API to become healthy"
$healthy = $false
$deadline = (Get-Date).AddSeconds(240)
do {
    Start-Sleep -Seconds 5
    $status = Invoke-Native -Exe "docker" -Arguments @("compose", "ps", "backend", "--format", "{{.Status}}")
    $healthy = ($status.Text -match "healthy")
} while (-not $healthy -and (Get-Date) -lt $deadline)
if (-not $healthy) {
    $null = Invoke-Native -Exe "docker" -Arguments @("compose", "logs", "backend", "--tail", "40")
    Pop-Location
    Stop-Demo "the API never became healthy"
}
Ok "backend healthy"

Say "applying migrations and demo data"
$migrate = Invoke-Native -Exe "docker" -Arguments @("compose", "exec", "-T", "backend", "python", "manage.py", "migrate", "--noinput")
if ($migrate.Code -ne 0) { Pop-Location; Stop-Demo "migrations failed:`n$($migrate.Text)" }
$seed = Invoke-Native -Exe "docker" -Arguments @("compose", "exec", "-T", "backend", "python", "manage.py", "seed_demo")
if ($seed.Code -ne 0) { Pop-Location; Stop-Demo "seeding failed:`n$($seed.Text)" }
Ok "demo data ready"

Say "final check"
$health = & curl.exe -s "http://localhost:$Port/health/" 2>$null
$appCode = & curl.exe -s -o NUL -w "%{http_code}" "http://localhost:$Port/" 2>$null
Pop-Location

Write-Host ""
Say "READY - open this in the browser"
Ok "App      : http://localhost:$Port"
Ok "API docs : http://localhost:$Port/api/docs/"
Ok "Login    : $demoEmail / $demoPassword   (admin@example.com for the audit view)"
Ok "Health   : $health"
Ok "Shell    : HTTP $appCode"
Write-Host ""
Warn "Stop with:  docker compose down        (data kept)"
Warn "Full reset: docker compose down -v     (data deleted)"
Warn "Worker log: docker compose logs worker | Select-String send_notification"