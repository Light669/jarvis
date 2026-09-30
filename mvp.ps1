#Requires -Version 5.1
<#
.SYNOPSIS
  MVP Orchestra : tout tester en une commande, sans rien installer au préalable.
.DESCRIPTION
  - Utilise Python 3.11+ s'il est installé ; sinon télécharge un Python PORTABLE dans le dossier
    (.runtime\python), sans installation ni droits administrateur.
  - Pas besoin de Docker, Node.js, Ollama ni de clé API.
  - Crée une organisation de démonstration et lance la simulation qui fait vivre la carte.
  - Ouvre le tableau de bord déjà connecté et crée un raccourci « Orchestra » sur le Bureau.
  - Tout est noté dans mvp-diagnostic.txt (à envoyer en cas de problème).
  Fermer la fenêtre (ou Ctrl+C) arrête tout.
.PARAMETER Reinitialiser
  Efface les données de démonstration (data, logs, Cerveau) et repart de zéro.
#>
param([switch]$Reinitialiser)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'   # rend les téléchargements beaucoup plus rapides sous PowerShell 5.1
Set-Location -Path $PSScriptRoot
$root = $PSScriptRoot
$IsWin = ($env:OS -eq 'Windows_NT')
$env:PYTHONUTF8 = '1'
$env:PIP_DISABLE_PIP_VERSION_CHECK = '1'
New-Item -ItemType Directory -Force -Path data, logs | Out-Null
$diag = Join-Path $root 'mvp-diagnostic.txt'
Set-Content -Path $diag -Value "Diagnostic Orchestra MVP — $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -Encoding UTF8
Add-Content -Path $diag -Value ("Windows : {0} | PowerShell : {1} | Dossier : {2}" -f [Environment]::OSVersion.VersionString, $PSVersionTable.PSVersion, $root)

function P([string[]]$parts) { return [IO.Path]::Combine([string[]](@($root) + $parts)) }
function Log($msg, $color = 'Gray') { Write-Host $msg -ForegroundColor $color; Add-Content -Path $diag -Value $msg }
function Step($msg) { Log "> $msg" 'Cyan' }
function Test-Cmd($name) { return [bool](Get-Command $name -ErrorAction SilentlyContinue) }

# Lance un programme externe : sortie copiée dans le diagnostic, code de retour renvoyé.
# (ErrorActionPreference passe à Continue : sous PowerShell 5.1, une ligne sur stderr ferait sinon échouer le script.)
function Invoke-Native([string]$exe, [string[]]$ArgList, [switch]$Show) {
  $old = $ErrorActionPreference
  $ErrorActionPreference = 'Continue'
  try {
    & $exe @ArgList 2>&1 | ForEach-Object {
      $line = "$_"
      Add-Content -Path $diag -Value $line
      if ($Show) { Write-Host $line -ForegroundColor DarkGray }
    }
    return $LASTEXITCODE
  } finally { $ErrorActionPreference = $old }
}

function Get-PyVersion([string[]]$cmd) {
  if (-not (Test-Cmd $cmd[0])) { return 0 }
  $old = $ErrorActionPreference
  $ErrorActionPreference = 'Continue'
  try {
    $out = & $cmd[0] @($cmd[1..9] + @('-c', 'import sys;print(sys.version_info[0]*100+sys.version_info[1])')) 2>$null
    if ($LASTEXITCODE -eq 0 -and "$out" -match '^\d+$') { return [int]"$out" }
  } catch {} finally { $ErrorActionPreference = $old }
  return 0
}

$server = $null
$notif = $null
$failed = $false
try {
  Write-Host ''
  Log '  ORCHESTRA — MVP de démonstration' 'Cyan'
  Log '  ---------------------------------' 'DarkGray'

  # 0. Déjà lancé ? On ouvre simplement le navigateur.
  $port = 8765
  try {
    $cfgPort = (Select-String -Path (P 'config.yaml') -Pattern '^\s*port:\s*(\d+)' | Select-Object -First 1).Matches[0].Groups[1].Value
    if ($cfgPort) { $port = [int]$cfgPort }
  } catch {}

  if ($Reinitialiser) {
    $ans = Read-Host 'Effacer data, logs et Cerveau (données de démonstration) ? [o/N]'
    if ($ans -match '^[oOyY]') {
      Remove-Item -Recurse -Force data, logs, Cerveau -ErrorAction SilentlyContinue
      New-Item -ItemType Directory -Force -Path data, logs | Out-Null
    }
  }

  # 1. Python : installé (3.11+) ou portable
  $pyExe = $null
  $portable = P '.runtime','python','python.exe'
  if ($IsWin -and (Test-Path $portable)) {
    $pyExe = $portable
    Log 'Python portable déjà présent.'
  } else {
    $sys = $null
    foreach ($cand in @(@('py', '-3.13'), @('py', '-3.12'), @('py', '-3.11'), @('python'), @('python3'))) {
      $v = Get-PyVersion $cand
      if ($v -ge 311) { $sys = $cand; Log ("Python trouvé : {0} ({1}.{2})" -f ($cand -join ' '), [int]($v / 100), ($v % 100)); break }
    }
    if ($sys) {
      $venvPy = if ($IsWin) { P '.venv','Scripts','python.exe' } else { P '.venv','bin','python' }
      if (-not (Test-Path $venvPy)) {
        Step 'Création de l''environnement Python (une seule fois)…'
        $code = Invoke-Native $sys[0] @($sys[1..9] + @('-m', 'venv', (P '.venv')))
        if ($code -ne 0 -or -not (Test-Path $venvPy)) { throw 'Impossible de créer l''environnement Python (.venv).' }
      }
      $pyExe = $venvPy
    } elseif ($IsWin) {
      # Pas de Python utilisable : Python portable officiel (python.org), dans le dossier, sans installation.
      [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
      $ver = '3.12.10'
      $arch = if ($env:PROCESSOR_ARCHITECTURE -eq 'ARM64') { 'arm64' } else { 'amd64' }
      $rt = P '.runtime','python'
      Step "Python n'est pas installé : téléchargement de Python $ver portable (≈ 11 Mo, sans installation)…"
      $zip = P '.runtime',"python-$ver-embed-$arch.zip"
      New-Item -ItemType Directory -Force -Path $rt | Out-Null
      Invoke-WebRequest -UseBasicParsing -Uri "https://www.python.org/ftp/python/$ver/python-$ver-embed-$arch.zip" -OutFile $zip
      Expand-Archive -Path $zip -DestinationPath $rt -Force
      Remove-Item $zip -Force
      # Active site-packages et rend le code d'Orchestra importable (fichier ._pth du Python portable)
      $pth = Get-ChildItem -Path $rt -Filter 'python*._pth' | Select-Object -First 1
      $lines = @(Get-Content $pth.FullName | ForEach-Object { if ($_ -match '^\s*#\s*import site') { 'import site' } else { $_ } })
      $lines += '..\..\platform'
      Set-Content -Path $pth.FullName -Value $lines -Encoding ASCII
      Step 'Installation de pip dans le Python portable…'
      $getpip = Join-Path $rt 'get-pip.py'
      Invoke-WebRequest -UseBasicParsing -Uri 'https://bootstrap.pypa.io/get-pip.py' -OutFile $getpip
      $code = Invoke-Native (Join-Path $rt 'python.exe') @($getpip, '--no-warn-script-location', '-q')
      if ($code -ne 0) { throw 'Installation de pip impossible (connexion Internet ?).' }
      $pyExe = Join-Path $rt 'python.exe'
    } else {
      throw 'Python 3.11+ est nécessaire (sudo apt install python3 python3-venv, ou brew install python).'
    }
  }

  # 2. Dépendances (une seule fois, puis à chaque mise à jour de platform\pyproject.toml)
  $stamp = P 'data','.deps-installed'
  if (-not (Test-Path $stamp) -or ((Get-Item -Force (P 'platform','pyproject.toml')).LastWriteTime -gt (Get-Item -Force $stamp).LastWriteTime)) {
    Step 'Installation des dépendances (1 à 3 minutes la première fois)…'
    if ($pyExe -eq $portable -or $pyExe -like '*.runtime*') {
      # Python portable : le code est déjà importable via le fichier ._pth, on installe seulement les dépendances
      $code = Invoke-Native $pyExe @('-m', 'pip', 'install', '-q', '--no-warn-script-location',
        'fastapi>=0.110', 'uvicorn[standard]>=0.29', 'pydantic>=2.6', 'pyyaml>=6', 'httpx>=0.27', 'watchdog>=4')
    } else {
      $code = Invoke-Native $pyExe @('-m', 'pip', 'install', '-q', '-e', (P 'platform'))
    }
    if ($code -ne 0) {
      # Repli : dépendances minimales en Python pur (sans les accélérateurs compilés de uvicorn[standard])
      Log 'Première tentative échouée : installation minimale…' 'Yellow'
      $code = Invoke-Native $pyExe @('-m', 'pip', 'install', '-q', '--no-warn-script-location',
        'fastapi>=0.110', 'uvicorn>=0.29', 'websockets>=12', 'pydantic>=2.6', 'pyyaml>=6', 'httpx>=0.27', 'watchdog>=4')
      if ($code -eq 0 -and -not ($pyExe -like '*.runtime*')) {
        $code = Invoke-Native $pyExe @('-m', 'pip', 'install', '-q', '--no-deps', '-e', (P 'platform'))
      }
    }
    if ($code -ne 0) { throw 'Installation des dépendances impossible (connexion Internet, proxy ou antivirus ?).' }
    if ($IsWin) { Invoke-Native $pyExe @('-m', 'pip', 'install', '-q', '--no-warn-script-location', 'win11toast') | Out-Null }
    New-Item -ItemType File -Force -Path $stamp | Out-Null
  }
  $code = Invoke-Native $pyExe @('-c', 'import orchestra, fastapi, uvicorn; print("imports OK")')
  if ($code -ne 0) { throw 'Le code d''Orchestra ne se charge pas (voir mvp-diagnostic.txt).' }

  # 3. Jeton local
  if (-not (Test-Path .env)) { Copy-Item .env.example .env }
  $envText = Get-Content .env -Raw -Encoding UTF8
  if ($envText -notmatch '(?m)^ORCHESTRA_TOKEN=\S+') {
    $bytes = New-Object byte[] 32
    [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    $tok = -join ($bytes | ForEach-Object { $_.ToString('x2') })
    if ($envText -match '(?m)^ORCHESTRA_TOKEN=') { $envText = $envText -replace '(?m)^ORCHESTRA_TOKEN=.*$', "ORCHESTRA_TOKEN=$tok" }
    else { $envText += "`r`nORCHESTRA_TOKEN=$tok" }
    Set-Content -Path .env -Value $envText -Encoding UTF8
  }
  $token = ([regex]::Match((Get-Content .env -Raw), '(?m)^ORCHESTRA_TOKEN=(\S+)')).Groups[1].Value
  $url = "http://127.0.0.1:$port/#token=$token"

  # 4. Déjà en marche ? (deuxième double-clic) -> on ouvre juste le navigateur
  $running = $false
  try { Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:$port/api/health" -TimeoutSec 2 | Out-Null; $running = $true } catch {}
  if ($running) {
    Log 'Orchestra tourne déjà : ouverture du navigateur.' 'Green'
    try { Start-Process $url } catch { Log "Ouvrez ce lien : $url" 'Yellow' }
    return
  }

  # 5. Coffre + organisation de démonstration
  Step 'Préparation du coffre et de la base…'
  if ((Invoke-Native $pyExe @('-m', 'orchestra', 'init')) -ne 0) { throw 'Initialisation d''Orchestra impossible.' }
  $countFile = P 'data','.agents-count'
  Invoke-Native $pyExe @('-c', "from orchestra.platform import Platform; p=Platform('.'); open(r'$countFile','w').write(str(len(p.agents.list()))); p.close()") | Out-Null
  $count = if (Test-Path $countFile) { [int](Get-Content $countFile -Raw) } else { 0 }
  if ($count -eq 0) {
    Step 'Création de l''organisation de démonstration…'
    if ((Invoke-Native $pyExe @('-m', 'orchestra', 'demo')) -ne 0) { throw 'Création de la démonstration impossible.' }
  }
  if (-not (Test-Path (P 'platform','dashboard','dist','index.html'))) {
    throw 'Tableau de bord absent (platform\dashboard\dist) : re-téléchargez le ZIP complet.'
  }

  # 6. Raccourci sur le Bureau (une fois)
  if ($IsWin) {
    try {
      $lnk = Join-Path ([Environment]::GetFolderPath('Desktop')) 'Orchestra.lnk'
      if (-not (Test-Path $lnk)) {
        $sc = (New-Object -ComObject WScript.Shell).CreateShortcut($lnk)
        $sc.TargetPath = P 'MVP.bat'
        $sc.WorkingDirectory = $root
        $sc.Description = 'Lancer Orchestra (MVP)'
        $sc.Save()
        Log 'Raccourci « Orchestra » créé sur le Bureau.' 'Green'
      }
    } catch { Add-Content -Path $diag -Value "Raccourci non créé : $($_.Exception.Message)" }
  }

  # 7. Lancement
  Step 'Démarrage d''Orchestra…'
  $server = Start-Process -FilePath $pyExe -ArgumentList '-m', 'orchestra', 'serve' -WorkingDirectory $root -NoNewWindow -PassThru
  $notifier = P 'platform','notifier','notifier.py'
  if ($IsWin -and (Test-Path $notifier)) {
    try { $notif = Start-Process -FilePath $pyExe -ArgumentList "`"$notifier`"" -WorkingDirectory $root -WindowStyle Hidden -PassThru } catch {}
  }
  $ok = $false
  for ($i = 0; $i -lt 90; $i++) {
    Start-Sleep -Milliseconds 500
    if ($server.HasExited) { break }
    try { Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:$port/api/health" -TimeoutSec 2 | Out-Null; $ok = $true; break } catch {}
  }
  if (-not $ok) { throw "Le serveur ne démarre pas sur le port $port (déjà utilisé par un autre programme ?)." }
  try { Start-Process $url } catch {}
  Write-Host ''
  Log '  Orchestra est ouvert dans votre navigateur.' 'Green'
  Log "  Si rien ne s'affiche, ouvrez ce lien : $url" 'Green'
  Log '  Laissez cette fenêtre ouverte. Ctrl+C ou fermer la fenêtre pour tout arrêter.' 'DarkGray'
  Write-Host ''
  Wait-Process -Id $server.Id
} catch {
  $failed = $true
  Write-Host ''
  Log ("ERREUR : " + $_.Exception.Message) 'Red'
  Add-Content -Path $diag -Value ($_ | Out-String)
  Write-Host ''
  Write-Host "Le détail est dans : $diag" -ForegroundColor Yellow
  Write-Host 'Envoyez ce fichier (ou une capture de cette fenêtre) pour que le problème soit corrigé.' -ForegroundColor Yellow
} finally {
  foreach ($p in @($server, $notif)) {
    if ($p -and -not $p.HasExited) { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue }
  }
  if ($server) { Write-Host 'Orchestra est arrêté.' -ForegroundColor Yellow }
}
if ($failed) { exit 1 }
