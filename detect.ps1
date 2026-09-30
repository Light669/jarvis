#Requires -Version 5.1
<#
.SYNOPSIS
  Détecte la configuration du PC et les prérequis d'Orchestra.
.DESCRIPTION
  - OS, CPU, RAM, GPU / VRAM
  - Présence de Docker Desktop (WSL2), Git, Node.js LTS, Python 3.11+, Ollama
  - Recommande le modèle local et le nombre d'agents actifs simultanés
  - Écrit le résultat dans docs\machine.md
  -Install : installe les prérequis manquants via winget (confirmation demandée)
  -Apply   : reporte les recommandations dans config.yaml (modèle par défaut, max_active_agents)
#>
param(
  [switch]$Install,
  [switch]$Apply
)

$ErrorActionPreference = 'Stop'
Set-Location -Path $PSScriptRoot

function Test-Cmd($name) { return [bool](Get-Command $name -ErrorAction SilentlyContinue) }
function Get-Ver($cmd, $argList) {
  try { return (& $cmd @argList 2>$null | Select-Object -First 1).ToString().Trim() } catch { return $null }
}

Write-Host "=== Orchestra : détection de la machine ===" -ForegroundColor Cyan

$os   = Get-CimInstance Win32_OperatingSystem
$cpu  = Get-CimInstance Win32_Processor | Select-Object -First 1
$ramGB = [math]::Round($os.TotalVisibleMemorySize / 1MB, 1)
$gpus = @(Get-CimInstance Win32_VideoController)

# VRAM : AdapterRAM est plafonné à 4 Go (uint32) ; on tente nvidia-smi pour une valeur exacte.
$vramGB = 0
if (Test-Cmd 'nvidia-smi') {
  try {
    $mb = (& nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits | Select-Object -First 1)
    $vramGB = [math]::Round([double]$mb / 1024, 1)
  } catch {}
}
if ($vramGB -eq 0) {
  $vramGB = [math]::Round((($gpus | Measure-Object -Property AdapterRAM -Maximum).Maximum) / 1GB, 1)
}

$tools = [ordered]@{
  'Git'            = @{ ok = (Test-Cmd git);    ver = (Get-Ver git @('--version'));    winget = 'Git.Git' }
  'Node.js LTS'    = @{ ok = (Test-Cmd node);   ver = (Get-Ver node @('--version'));   winget = 'OpenJS.NodeJS.LTS' }
  'Python 3.11+'   = @{ ok = $false;            ver = $null;                           winget = 'Python.Python.3.12' }
  'Docker Desktop' = @{ ok = (Test-Cmd docker); ver = (Get-Ver docker @('--version')); winget = 'Docker.DockerDesktop' }
  'Ollama'         = @{ ok = (Test-Cmd ollama); ver = (Get-Ver ollama @('--version')); winget = 'Ollama.Ollama' }
}
foreach ($py in @('py', 'python')) {
  if (Test-Cmd $py) {
    $v = if ($py -eq 'py') { Get-Ver py @('-3', '--version') } else { Get-Ver python @('--version') }
    if ($v -match 'Python (\d+)\.(\d+)') {
      if ([int]$Matches[1] -eq 3 -and [int]$Matches[2] -ge 11) { $tools['Python 3.11+'].ok = $true; $tools['Python 3.11+'].ver = $v; break }
    }
  }
}

$wsl = $false
try { $wsl = [bool](wsl.exe --status 2>$null) } catch {}

# Recommandations de dimensionnement
if ($vramGB -ge 12)      { $model = 'ollama/qwen2.5:14b'; $agents = 4 }
elseif ($vramGB -ge 8)   { $model = 'ollama/qwen2.5:7b';  $agents = 3 }
elseif ($ramGB -ge 32)   { $model = 'ollama/qwen2.5:7b';  $agents = 3 }
elseif ($ramGB -ge 16)   { $model = 'ollama/qwen2.5:7b';  $agents = 2 }
else                     { $model = 'ollama/qwen2.5:3b';  $agents = 1 }

Write-Host ("OS       : {0} ({1})" -f $os.Caption, $os.Version)
Write-Host ("CPU      : {0} ({1} coeurs logiques)" -f $cpu.Name.Trim(), $cpu.NumberOfLogicalProcessors)
Write-Host ("RAM      : {0} Go" -f $ramGB)
foreach ($g in $gpus) { Write-Host ("GPU      : {0}" -f $g.Name) }
Write-Host ("VRAM max : {0} Go" -f $vramGB)
Write-Host ("WSL2     : {0}" -f ($(if ($wsl) { 'présent' } else { 'non détecté' })))
Write-Host ""
$missing = @()
foreach ($k in $tools.Keys) {
  $t = $tools[$k]
  if ($t.ok) { Write-Host ("[OK]      {0,-15} {1}" -f $k, $t.ver) -ForegroundColor Green }
  else       { Write-Host ("[MANQUE]  {0,-15} winget install {1}" -f $k, $t.winget) -ForegroundColor Yellow; $missing += $k }
}
Write-Host ""
Write-Host ("Modèle local recommandé : {0}" -f $model) -ForegroundColor Cyan
Write-Host ("Agents actifs simultanés : {0}" -f $agents) -ForegroundColor Cyan

$lines = @(
  '# Machine du Propriétaire', '',
  "_Généré par detect.ps1 le $(Get-Date -Format 'yyyy-MM-dd HH:mm')_", '',
  '| Élément | Valeur |', '|---|---|',
  "| OS | $($os.Caption) $($os.Version) |",
  "| CPU | $($cpu.Name.Trim()) ($($cpu.NumberOfLogicalProcessors) threads) |",
  "| RAM | $ramGB Go |",
  "| GPU | $(($gpus | ForEach-Object { $_.Name }) -join ', ') |",
  "| VRAM max | $vramGB Go |",
  "| WSL2 | $wsl |", '',
  '## Prérequis', '', '| Outil | Présent | Version | Installation |', '|---|---|---|---|'
)
foreach ($k in $tools.Keys) { $t = $tools[$k]; $lines += "| $k | $($t.ok) | $($t.ver) | winget install $($t.winget) |" }
$lines += @('', '## Recommandations', '', "- Modèle local par défaut : ``$model``", "- Agents actifs simultanés : **$agents**",
  "- Télécharger le modèle : ``ollama pull $($model -replace '^ollama/', '')``")
New-Item -ItemType Directory -Force -Path docs | Out-Null
$lines -join "`r`n" | Set-Content -Encoding UTF8 docs\machine.md
Write-Host "Rapport écrit dans docs\machine.md"

if ($Apply) {
  $cfg = Get-Content config.yaml -Raw -Encoding UTF8
  $cfg = $cfg -replace '(?m)^(\s*default_model:\s*).*$', "`${1}$model"
  $cfg = $cfg -replace '(?m)^(\s*max_active_agents:\s*)\d+', "`${1}$agents"
  $cfg | Set-Content -Encoding UTF8 config.yaml
  Write-Host "config.yaml mis à jour (default_model, max_active_agents)." -ForegroundColor Green
}

if ($Install -and $missing.Count -gt 0) {
  if (-not (Test-Cmd winget)) { Write-Host 'winget introuvable : installez les outils manuellement.' -ForegroundColor Red; exit 1 }
  foreach ($k in $missing) {
    $id = $tools[$k].winget
    $ans = Read-Host "Installer $k ($id) ? [o/N]"
    if ($ans -match '^[oOyY]') { winget install --id $id -e --accept-source-agreements --accept-package-agreements }
  }
  Write-Host 'Redémarrez le terminal pour prendre en compte les nouveaux outils.' -ForegroundColor Cyan
}
