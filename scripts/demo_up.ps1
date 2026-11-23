# demo_up.ps1 - one command to get a presentable stack running.
#
# Why this exists: the presentation must not depend on remembering twelve steps, on port 8080 being
# free, or on Docker Desktop already running. This script checks and fixes each of those, and prints
# exactly what to open.
#
#   powershell -ExecutionPolicy Bypass -File scripts\demo_up.ps1
#
# Options:
#   -Port 8090        host port for the app (Nginx). Default: first free port from 8090 upwards.
#   -SkipBuild        reuse the existing images instead of rebuilding (faster; use when nothing changed)
#   -Reseed           wipe the database volume and recreate the demo data (clean slate for the demo)
#   -LocalOnly        skip Docker entirely and start the Django dev server + Vite instead
#
# It never destroys data unless -Reseed is passed.

[CmdletBinding()]
param(
    [int]$Port = 0,
    [switch]$SkipBuild,
    [switch]$Reseed,
    [switch]$LocalOnly
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $repo ".env"
$demoEmail = "manager@example.com"
$demoPassword = "Demo!Passw0rd"

function Say($message) { Write-Host "== $message" -ForegroundColor Cyan }
function Ok($message) { Write-Host "   $message" -ForegroundColor Green }
function Warn($message) { Write-Host "   $message" -ForegroundColor Yellow }
function Die($message) { Write-Host "FAILED: $message" -ForegroundColor Red; exit 1 }

function Test-PortFree([int]$candidate) {
    $listening = Get-NetTCPConnection -LocalPort $candidate -State Listen -ErrorAction SilentlyContinue
    return -not $listening
}

function Find-FreePort {
    foreach ($candidate in 8090..8120) { if (Test-PortFree $candidate) { return $candidate } }
    Die "no free port between 8090 and 8120"
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
    if (-not (Test-Path $python)) { Die "backend\.venv is missing; see docs/development/development-guide.md" }

    $backendPort = 8000
    if (-not (Test-PortFree $backendPort)) { Die "port $backendPort is busy; stop whatever uses it" }
    $frontendPort = 5173
    if (-not (Test-PortFree $frontendPort)) { Die "port $frontendPort is busy; stop whatever uses it" }

    Push-Location (Join-Path $repo "backend")
    & $python manage.py migrate --noinput | Out-Null
    $users = & $python -c "import os;os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings.development');import django;django.setup();from apps.accounts.models import User;print(User.objects.count())"
    if ($users.Trim() -eq "0" -or $Reseed) { & $python manage.py seed_demo | Out-Null; Ok "demo data created" }
    Pop-Location

    Start-Process -FilePath $python -ArgumentList "manage.py", "runserver", "127.0.0.1:8000", "--noreload" `
        -WorkingDirectory (Join-Path $repo "backend") -WindowStyle Minimized
    Start-Process -FilePath "pnpm" -ArgumentList "dev" -WorkingDirectory (Join-Path $repo "frontend") -WindowStyle Minimized

    Start-Sleep -Seconds 8
    Say "ready"
    Ok "App     : http://localhost:$frontendPort"
    Ok "API docs: http://127.0.0.1:$backendPort/api/docs/"
    Ok "Login   : $demoEmail / $demoPassword"
    Warn "Two windows were started (Django + Vite). Close them to stop."
    exit 0
}

# ---------------------------------------------------------------------------
# Container stack
# ---------------------------------------------------------------------------
Say "checking Docker"
$null = docker version --format '{{.Server.Version}}' 2>$null
if ($LASTEXITCODE -ne 0) {
    $desktop = Join-Path $env:LOCALAPPDATA "Programs\DockerDesktop\Docker Desktop.exe"
    if (-not (Test-Path $desktop)) { Die "Docker Desktop not found; run with -LocalOnly instead" }
    Warn "Docker daemon is not running; starting Docker Desktop"
    Start-Process -FilePath $desktop | Out-Null
    $deadline = (Get-Date).AddSeconds(240)
    do {
        Start-Sleep -Seconds 8
        $null = docker version --format '{{.Server.Version}}' 2>$null
        $up = ($LASTEXITCODE -eq 0)
    } while (-not $up -and (Get-Date) -lt $deadline)
    if (-not $up) { Die "Docker did not start within 4 minutes; run with -LocalOnly instead" }
}
Ok "docker $(docker version --format '{{.Server.Version}}')"

Say "choosing a host port"
if ($Port -eq 0) { $Port = Find-FreePort }
elseif (-not (Test-PortFree $Port)) { Die "port $Port is already in use" }
if (-not (Test-Path $envFile)) { Die ".env is missing; copy .env.example to .env first" }
Set-EnvValue "NGINX_PORT" "$Port"
Set-EnvValue "S3_PORT_HOST" "$(if (Test-PortFree 9090) { 9090 } else { 9091 })"
Ok "app will be published on http://localhost:$Port"

Push-Location $repo
if ($Reseed) {
    Say "resetting the stack and its data (-Reseed)"
    docker compose down -v --remove-orphans | Out-Null
}

Say "building and starting the stack (first run takes a few minutes)"
if ($SkipBuild) { docker compose up -d } else { docker compose up -d --build }
if ($LASTEXITCODE -ne 0) { Pop-Location; Die "docker compose up failed; see the output above" }

Say "waiting for the API to become healthy"
$deadline = (Get-Date).AddSeconds(180)
do {
    Start-Sleep -Seconds 5
    $status = docker compose ps backend --format "{{.Status}}" 2>$null
    $healthy = $status -match "healthy"
} while (-not $healthy -and (Get-Date) -lt $deadline)
if (-not $healthy) { docker compose logs backend --tail 30; Pop-Location; Die "the API never became healthy" }
Ok "backend healthy"

Say "applying migrations and demo data"
docker compose exec -T backend python manage.py migrate --noinput | Out-Null
docker compose exec -T backend python manage.py seed_demo | Out-Null
Ok "demo data ready"

Say "final check"
$health = curl.exe -s "http://localhost:$Port/health/"
$app = curl.exe -s -o NUL -w "%{http_code}" "http://localhost:$Port/"
Pop-Location

Write-Host ""
Say "READY - open this in the browser"
Ok "App      : http://localhost:$Port"
Ok "API docs : http://localhost:$Port/api/docs/"
Ok "Login    : $demoEmail / $demoPassword   (admin@example.com for the audit view)"
Ok "Health   : $health   (app shell HTTP $app)"
Write-Host ""
Warn "Stop with:  docker compose down          (data kept)"
Warn "Full reset: docker compose down -v       (data deleted)"
Warn "Check the worker:  docker compose logs worker | Select-String send_notification"