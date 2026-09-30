#Requires -Version 5.1
<#
.SYNOPSIS
  MVP Orchestra : tout tester en une commande, avec Python pour seul prérequis.
.DESCRIPTION
  - Pas besoin de Docker, Node.js, Ollama ni de clé API.
  - Crée une organisation de démonstration (9 agents) au premier lancement.
  - Lance la simulation qui fait vivre la carte (tâches, messages, demandes, refus).
  - Ouvre le tableau de bord déjà connecté. Fermer la fenêtre (ou Ctrl+C) arrête tout.
.PARAMETER Reinitialiser
  Efface les données de démonstration (data, logs, Cerveau) et repart de zéro.
#>
param([switch]$Reinitialiser)

$ErrorActionPreference = 'Stop'
Set-Location -Path $PSScriptRoot
$root = $PSScriptRoot
function Test-Cmd($name) { return [bool](Get-Command $name -ErrorAction SilentlyContinue) }

Write-Host ''
Write-Host '  ORCHESTRA — MVP de démonstration' -ForegroundColor Cyan
Write-Host '  ---------------------------------' -ForegroundColor DarkGray

# 1. Python 3.11+
$py = $null
foreach ($cand in @(@('py', '-3.13'), @('py', '-3.12'), @('py', '-3.11'), @('python'), @('python3'))) {
  if (Test-Cmd $cand[0]) {
    try {
      $v = & $cand[0] @($cand[1..9] + @('-c', 'import sys;print(sys.version_info[0]*100+sys.version_info[1])')) 2>$null
      if ([int]$v -ge 311) { $py = $cand; break }
    } catch {}
  }
}
if (-not $py) {
  Write-Host 'Python 3.11 ou plus récent est nécessaire.' -ForegroundColor Yellow
  if (Test-Cmd winget) {
    $ans = Read-Host 'Installer Python 3.12 maintenant avec winget ? [o/N]'
    if ($ans -match '^[oOyY]') {
      winget install --id Python.Python.3.12 -e --accept-source-agreements --accept-package-agreements
      Write-Host 'Python est installé : fermez cette fenêtre et relancez MVP.bat.' -ForegroundColor Green
    }
  } else { Write-Host 'Téléchargez-le sur https://www.python.org/downloads/ (cochez « Add python.exe to PATH »).' }
  Read-Host 'Entrée pour quitter'; exit 1
}

# 2. Réinitialisation éventuelle
if ($Reinitialiser) {
  $ans = Read-Host 'Effacer data, logs et Cerveau (données de démonstration) ? [o/N]'
  if ($ans -match '^[oOyY]') { Remove-Item -Recurse -Force data, logs, Cerveau -ErrorAction SilentlyContinue }
}
New-Item -ItemType Directory -Force -Path data, logs | Out-Null

# 3. Environnement Python
$venvPy = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path $venvPy)) {
  Write-Host '> Création de l''environnement Python (une seule fois)…' -ForegroundColor Cyan
  & $py[0] @($py[1..9] + @('-m', 'venv', '.venv'))
}
$stamp = 'data\.deps-installed'
if (-not (Test-Path $stamp) -or ((Get-Item platform\pyproject.toml).LastWriteTime -gt (Get-Item $stamp).LastWriteTime)) {
  Write-Host '> Installation des dépendances (1 à 2 minutes la première fois)…' -ForegroundColor Cyan
  & $venvPy -m pip install -q --disable-pip-version-check --upgrade pip
  & $venvPy -m pip install -q --disable-pip-version-check -e "platform[windows]"
  if ($LASTEXITCODE -ne 0) { & $venvPy -m pip install -q --disable-pip-version-check -e platform }
  if ($LASTEXITCODE -ne 0) { throw 'Installation des dépendances impossible (connexion Internet ?)' }
  New-Item -ItemType File -Force -Path $stamp | Out-Null
}

# 4. Jeton local
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
$envText = Get-Content .env -Raw -Encoding UTF8
if ($envText -notmatch '(?m)^ORCHESTRA_TOKEN=\S+') {
  $bytes = New-Object byte[] 32; [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
  $tok = -join ($bytes | ForEach-Object { $_.ToString('x2') })
  $envText = $envText -replace '(?m)^ORCHESTRA_TOKEN=.*$', "ORCHESTRA_TOKEN=$tok"
  if ($envText -notmatch 'ORCHESTRA_TOKEN=') { $envText += "`r`nORCHESTRA_TOKEN=$tok" }
  $envText | Set-Content -Encoding UTF8 .env
}
$token = ([regex]::Match((Get-Content .env -Raw), '(?m)^ORCHESTRA_TOKEN=(\S+)')).Groups[1].Value

# 5. Coffre + organisation de démonstration
$env:PYTHONUTF8 = '1'
& $venvPy -m orchestra init | Out-Null
$count = & $venvPy -c "from orchestra.platform import Platform; p=Platform('.'); print(len(p.agents.list())); p.close()"
if ([int]$count -eq 0) {
  Write-Host '> Création de l''organisation de démonstration…' -ForegroundColor Cyan
  & $venvPy -m orchestra demo
}
$port = & $venvPy -c "from orchestra.config import load_config; print(load_config('.').server.port)"

# 6. Lancement
if (-not (Test-Path platform\dashboard\dist\index.html)) { throw 'Tableau de bord absent (platform\dashboard\dist) : re-téléchargez le dépôt.' }
Write-Host '> Démarrage…' -ForegroundColor Cyan
$server = Start-Process -FilePath $venvPy -ArgumentList '-m', 'orchestra', 'serve' -NoNewWindow -PassThru
$notif = Start-Process -FilePath $venvPy -ArgumentList (Join-Path $root 'platform\notifier\notifier.py') -WindowStyle Hidden -PassThru
try {
  $ok = $false
  for ($i = 0; $i -lt 60; $i++) {
    Start-Sleep -Milliseconds 500
    try { Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:$port/api/health" -TimeoutSec 2 | Out-Null; $ok = $true; break } catch {}
  }
  if (-not $ok) { throw "L'API ne répond pas sur le port $port (déjà utilisé ?)" }
  Start-Process "http://127.0.0.1:$port/#token=$token"
  Write-Host ''
  Write-Host "  Orchestra tourne : http://127.0.0.1:$port" -ForegroundColor Green
  Write-Host '  Le navigateur s''est ouvert. Laissez cette fenêtre ouverte.' -ForegroundColor Green
  Write-Host '  Ctrl+C ou fermer la fenêtre pour tout arrêter.' -ForegroundColor DarkGray
  Write-Host ''
  Wait-Process -Id $server.Id
} finally {
  foreach ($p in @($server, $notif)) { if ($p -and -not $p.HasExited) { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue } }
  Write-Host 'Orchestra est arrêté.' -ForegroundColor Yellow
}
