#Requires -Version 5.1
<#
.SYNOPSIS
  Lance toute la plateforme Orchestra en une commande.
.PARAMETER Rebuild
  Force la reconstruction du tableau de bord et de l'image runtime.
.PARAMETER NoBrowser
  N'ouvre pas le navigateur.
#>
param([switch]$Rebuild, [switch]$NoBrowser)

$ErrorActionPreference = 'Stop'
Set-Location -Path $PSScriptRoot
$root = $PSScriptRoot
New-Item -ItemType Directory -Force -Path data, logs | Out-Null

function Test-Cmd($name) { return [bool](Get-Command $name -ErrorAction SilentlyContinue) }

# 0. Déjà lancé ?
if (Test-Path data\orchestra.pid) {
  $old = Get-Content data\orchestra.pid
  if (Get-Process -Id $old -ErrorAction SilentlyContinue) { Write-Host "Orchestra tourne déjà (PID $old). Utilisez stop.ps1." -ForegroundColor Yellow; exit 0 }
}

# 1. Python (venv)
$py = if (Test-Cmd py) { 'py' } elseif (Test-Cmd python) { 'python' } else { throw 'Python 3.11+ introuvable : lancez .\detect.ps1 -Install' }
if (-not (Test-Path .venv\Scripts\python.exe)) {
  Write-Host '> Création de l''environnement Python (.venv)' -ForegroundColor Cyan
  if ($py -eq 'py') { & py -3 -m venv .venv } else { & python -m venv .venv }
}
$venvPy = Join-Path $root '.venv\Scripts\python.exe'
$stamp = 'data\.deps-installed'
if ($Rebuild -or -not (Test-Path $stamp) -or ((Get-Item platform\pyproject.toml).LastWriteTime -gt (Get-Item $stamp).LastWriteTime)) {
  Write-Host '> Installation des dépendances Python' -ForegroundColor Cyan
  & $venvPy -m pip install -q --upgrade pip
  & $venvPy -m pip install -q -e "platform[windows,dev]"
  New-Item -ItemType File -Force -Path $stamp | Out-Null
}

# 2. Secrets et jeton local
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
$envText = Get-Content .env -Raw -Encoding UTF8
if ($envText -notmatch '(?m)^ORCHESTRA_TOKEN=\S+') {
  $bytes = New-Object byte[] 32; [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
  $token = -join ($bytes | ForEach-Object { $_.ToString('x2') })
  $envText = $envText -replace '(?m)^ORCHESTRA_TOKEN=.*$', "ORCHESTRA_TOKEN=$token"
  if ($envText -notmatch 'ORCHESTRA_TOKEN=') { $envText += "`r`nORCHESTRA_TOKEN=$token" }
  $envText | Set-Content -Encoding UTF8 .env
  Write-Host '> Jeton local généré dans .env' -ForegroundColor Green
}
$token = ([regex]::Match((Get-Content .env -Raw), '(?m)^ORCHESTRA_TOKEN=(\S+)')).Groups[1].Value

# 3. Coffre Obsidian + base
& $venvPy -m orchestra init
if ($LASTEXITCODE -ne 0) { throw 'Initialisation échouée' }

# 4. Tableau de bord
if (Test-Cmd npm) {
  if ($Rebuild -or -not (Test-Path platform\dashboard\dist\index.html)) {
    Write-Host '> Construction du tableau de bord' -ForegroundColor Cyan
    Push-Location platform\dashboard
    npm ci --no-audit --no-fund; npm run build
    Pop-Location
  }
} else { Write-Host '! npm absent : tableau de bord non reconstruit' -ForegroundColor Yellow }

# 5. Image d'exécution isolée (Docker)
if (Test-Cmd docker) {
  docker info *> $null
  if ($LASTEXITCODE -eq 0) {
    $img = docker images -q orchestra-runtime:latest
    if ($Rebuild -or -not $img) { Write-Host '> Construction de l''image runtime' -ForegroundColor Cyan; docker compose --profile build-only build }
  } else { Write-Host '! Docker Desktop n''est pas démarré : isolation dégradée (sous-processus)' -ForegroundColor Yellow }
} else { Write-Host '! Docker absent : isolation dégradée (sous-processus)' -ForegroundColor Yellow }

# 6. Ollama (facultatif)
if (Test-Cmd ollama) {
  try { Invoke-WebRequest -UseBasicParsing http://127.0.0.1:11434/api/tags -TimeoutSec 2 | Out-Null }
  catch { Write-Host '> Démarrage d''Ollama' -ForegroundColor Cyan; Start-Process ollama -ArgumentList 'serve' -WindowStyle Hidden }
}

# 7. API (FastAPI + Scribe + planificateur) et notifier
Write-Host '> Démarrage de l''API Orchestra' -ForegroundColor Cyan
$api = Start-Process -FilePath $venvPy -ArgumentList '-m', 'orchestra', 'serve' -WorkingDirectory $root `
  -WindowStyle Hidden -PassThru -RedirectStandardOutput logs\api.out.txt -RedirectStandardError logs\api.err.txt
$api.Id | Set-Content data\orchestra.pid

$ok = $false
for ($i = 0; $i -lt 40; $i++) {
  Start-Sleep -Milliseconds 500
  try { Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8765/api/health -TimeoutSec 2 | Out-Null; $ok = $true; break } catch {}
}
if (-not $ok) { Write-Host 'L''API ne répond pas : voir logs\api.err.txt' -ForegroundColor Red; exit 1 }

$notif = Start-Process -FilePath $venvPy -ArgumentList (Join-Path $root 'platform\notifier\notifier.py') -WorkingDirectory $root -WindowStyle Hidden -PassThru
$notif.Id | Set-Content data\notifier.pid

$url = "http://127.0.0.1:8765/#token=$token"
Write-Host ''
Write-Host "Orchestra est lancé : http://127.0.0.1:8765" -ForegroundColor Green
Write-Host "Jeton : voir ORCHESTRA_TOKEN dans .env (le lien ci-dessous le transmet automatiquement)"
if (-not $NoBrowser) { Start-Process $url }
