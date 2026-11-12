# Word <-> Markdown tooling. Usage:  .\docx.ps1 seed | reference | export-wiki [--to-wiki] [--only 06,07]
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$py = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $py)) { & "$PSScriptRoot\build.ps1" --html-only | Out-Null }   # creates the venv
$env:Path += ';C:\Program Files\Pandoc;' + (Join-Path $env:LOCALAPPDATA 'Pandoc')
& $py docx_tools.py @args
exit $LASTEXITCODE
