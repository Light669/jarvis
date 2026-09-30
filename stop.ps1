#Requires -Version 5.1
<# Arrête proprement Orchestra : API, notifier, conteneurs d'agents. #>
$ErrorActionPreference = 'Continue'
Set-Location -Path $PSScriptRoot

function Stop-FromPid($file, $label) {
  if (Test-Path $file) {
    $procId = Get-Content $file
    $p = Get-Process -Id $procId -ErrorAction SilentlyContinue
    if ($p) {
      Write-Host "> Arrêt $label (PID $procId)"
      Stop-Process -Id $procId -ErrorAction SilentlyContinue
      $p.WaitForExit(10000) | Out-Null
      if (-not $p.HasExited) { Stop-Process -Id $procId -Force }
    }
    Remove-Item $file -Force
  }
}

# Arrêt gracieux : l'API enregistre l'arrêt dans les logs puis s'arrête.
$token = $null
if (Test-Path .env) { $token = ([regex]::Match((Get-Content .env -Raw), '(?m)^ORCHESTRA_TOKEN=(\S+)')).Groups[1].Value }
if ($token) {
  try {
    Invoke-WebRequest -UseBasicParsing -Method Post -Uri http://127.0.0.1:8765/api/system/shutdown `
      -Headers @{ Authorization = "Bearer $token" } -TimeoutSec 5 | Out-Null
    Start-Sleep -Seconds 2
  } catch {}
}

Stop-FromPid 'data\notifier.pid' 'du notifier'
Stop-FromPid 'data\orchestra.pid' 'de l''API'

if (Get-Command docker -ErrorAction SilentlyContinue) {
  $ids = docker ps -q --filter 'label=orchestra.sandbox=1' 2>$null
  if ($ids) { Write-Host '> Arrêt des conteneurs d''agents'; docker kill $ids | Out-Null }
}
Write-Host 'Orchestra est arrêté.' -ForegroundColor Green
