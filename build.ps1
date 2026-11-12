# Build the Galileo User Manual PDF on Windows.
# Usage:  .\build.ps1 [build_manual.py options]     e.g.  .\build.ps1 --only 06,07
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

$venv = Join-Path $PSScriptRoot '.venv'
$py   = Join-Path $venv 'Scripts\python.exe'

if (-not (Test-Path $py)) {
    Write-Host 'Creating virtual environment...'
    python -m venv $venv
    if ($LASTEXITCODE -ne 0) { throw 'python -m venv failed (is Python 3.11+ installed?)' }
}

# Re-install only when requirements.txt changed.
$stamp = Join-Path $venv '.requirements.hash'
$hash  = (Get-FileHash requirements.txt).Hash
if (-not (Test-Path $stamp) -or (Get-Content $stamp) -ne $hash) {
    Write-Host 'Installing dependencies...'
    & $py -m pip install --quiet --upgrade pip
    & $py -m pip install --quiet -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw 'pip install failed' }
    Set-Content $stamp $hash
}

& $py build_manual.py @args
exit $LASTEXITCODE
