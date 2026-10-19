[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$projectPath = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectPath '.venv\Scripts\python.exe'
$entryPath = Join-Path $projectPath 'background.py'
& $pythonPath $entryPath start
if ($LASTEXITCODE -ne 0) { throw 'Automation did not start. Check runtime logs and configuration.' }
& $pythonPath $entryPath status
