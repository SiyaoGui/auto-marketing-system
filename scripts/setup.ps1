$ErrorActionPreference = 'Stop'
$project = Split-Path -Parent $PSScriptRoot
Push-Location $project
try {
  python -m venv .venv
  if ($LASTEXITCODE -ne 0) { throw 'Could not create Python environment' }
  & '.\.venv\Scripts\python.exe' -m pip install -r requirements.txt
  if ($LASTEXITCODE -ne 0) { throw 'Dependencies not installed. Check internet access; no paid service is required.' }
  & '.\.venv\Scripts\python.exe' -m engine.cli doctor
} finally { Pop-Location }
