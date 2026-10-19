[CmdletBinding()]
param()
$projectPath = Split-Path -Parent $PSScriptRoot
& (Join-Path $projectPath '.venv\Scripts\python.exe') (Join-Path $projectPath 'background.py') stop
if ($LASTEXITCODE -ne 0) { throw 'Graceful shutdown did not finish; inspect runtime\automation.log.' }
