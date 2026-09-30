# ProductLens quickstart (Windows): venv -> install -> tests -> API on :8000.
# Usage: .\run.ps1 [-SkipTests]   Optional settings come from .env (see .env.example).
param([switch]$SkipTests)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path .venv)) { python -m venv .venv }
$py = ".venv\Scripts\python.exe"
& $py -m pip install -q --upgrade pip
& $py -m pip install -q -r api\requirements.txt
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

if (Test-Path .env) {
  Get-Content .env | ForEach-Object {
    $line = ($_ -replace '\s+#.*$', '').Trim()
    if ($line -and -not $line.StartsWith('#') -and $line.Contains('=')) {
      $k, $v = $line.Split('=', 2)
      [Environment]::SetEnvironmentVariable($k.Trim(), $v.Trim(), 'Process')
    }
  }
}

if (-not $SkipTests) {
  foreach ($s in 'analysis', 'benchmark', 'signals') {
    & $py -m unittest discover -s "$s/tests" -t .
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
  }
  foreach ($s in 'dataset/tests', 'api/tests') {
    & $py -m unittest discover -s $s
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
  }
}

if (-not (Test-Path web\dist\index.html) -and (Get-Command npm -ErrorAction SilentlyContinue)) {
  Push-Location web
  try { npm ci; if ($LASTEXITCODE -eq 0) { npm run build } } finally { Pop-Location }
  if ($LASTEXITCODE -ne 0) { Write-Host "web build failed; the API still works" }
}

$port = if ($env:PORT) { $env:PORT } else { '8000' }
Write-Host "Aparece API: http://127.0.0.1:$port/docs  app: http://127.0.0.1:$port/"
& $py -m uvicorn main:app --app-dir api --host 127.0.0.1 --port $port
