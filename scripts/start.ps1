param([switch]$Docker)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
if ($Docker) {
    docker compose up --build -d
    if ($LASTEXITCODE -ne 0) { throw 'Docker startup failed. Check that Docker Desktop is running.' }
    docker compose exec api harmonygraph catalog start
    Write-Host 'Open http://localhost:8080. The real-song catalog grows as processing completes.'
    exit
}
if (-not (Test-Path '.venv/Scripts/python.exe')) { python -m venv .venv }
& '.venv/Scripts/python.exe' -m pip install -r requirements-dev.lock
if ($LASTEXITCODE -ne 0) { throw 'Locked dependency installation failed.' }
& '.venv/Scripts/python.exe' -m pip install --no-deps -e .
if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed.' }
& '.venv/Scripts/python.exe' -m harmonygraph.cli migrate
if ($LASTEXITCODE -ne 0) { throw 'Database migration failed.' }
& '.venv/Scripts/python.exe' -m harmonygraph.cli catalog start
if ($LASTEXITCODE -ne 0) { throw 'Catalog startup failed.' }
Push-Location web
npm ci --cache .npm-cache
if ($LASTEXITCODE -ne 0) { throw 'Frontend installation failed.' }
Pop-Location
$pythonPath = Join-Path $projectRoot '.venv/Scripts/python.exe'
Start-Process -FilePath $pythonPath -ArgumentList '-m','harmonygraph.cli','serve' -WorkingDirectory $projectRoot -WindowStyle Hidden
Start-Process -FilePath $pythonPath -ArgumentList '-m','harmonygraph.jobs' -WorkingDirectory $projectRoot -WindowStyle Hidden
$env:JOB_KINDS = 'catalog_metadata'
Start-Process -FilePath $pythonPath -ArgumentList '-m','harmonygraph.jobs' -WorkingDirectory $projectRoot -WindowStyle Hidden
Remove-Item Env:JOB_KINDS
Start-Process -FilePath 'cmd.exe' -ArgumentList '/c','npm run dev' -WorkingDirectory (Join-Path $projectRoot 'web') -WindowStyle Hidden
Write-Host 'Open http://127.0.0.1:5173. API documentation: http://127.0.0.1:8000/docs'
