<# Run Install only when you want to register Windows login automation. #>
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)]
    [ValidateSet('Install', 'Verify', 'Disable', 'Uninstall')]
    [string]$Action
)
$ErrorActionPreference = 'Stop'
$projectPath = Split-Path -Parent $PSScriptRoot
$taskName = 'Smart Screenshot Organizer'
$entryPath = Join-Path $projectPath 'background.py'
$pythonPath = Join-Path $projectPath '.venv\Scripts\python.exe'
$pythonwPath = Join-Path $projectPath '.venv\Scripts\pythonw.exe'
function Get-OwnedTask {
    $found = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    if ($null -ne $found) {
        if ($found.Actions.Count -ne 1 -or $found.Actions[0].Execute -ne $pythonwPath -or $found.Actions[0].Arguments -ne ('"' + $entryPath + '" run')) {
            throw 'Task name belongs to a different command or project; refusing to change it.'
        }
    }
    return $found
}
switch ($Action) {
    'Install' {
        if (-not (Test-Path -LiteralPath $pythonwPath)) { throw 'Project virtual environment is missing.' }
        if (-not (Test-Path -LiteralPath (Join-Path $projectPath 'automation.json'))) {
            throw 'Run background.py configure first.'
        }
        if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
            throw 'A task with this name already exists. Verify it; uninstall it explicitly before replacing it.'
        }
        $userIdentity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
        $taskAction = New-ScheduledTaskAction -Execute $pythonwPath -Argument ('"' + $entryPath + '" run') -WorkingDirectory $projectPath
        $trigger = New-ScheduledTaskTrigger -AtLogOn -User $userIdentity
        $trigger.Delay = 'PT30S'
        $principal = New-ScheduledTaskPrincipal -UserId $userIdentity -LogonType Interactive -RunLevel Limited
        $taskSettings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
        Register-ScheduledTask -TaskName $taskName -Action $taskAction -Trigger $trigger -Principal $principal -Settings $taskSettings -Description 'Local copy-only screenshot automation at user login.' | Out-Null
        Write-Output 'Installed. Starts after your next login; use Start-Automation.ps1 to start now.'
    }
    'Verify' {
        $task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
        if ($null -eq $task) { Write-Output 'Startup task is not installed.' }
        else {
            $task | Select-Object TaskName, State
            $task.Actions | Select-Object Execute, Arguments, WorkingDirectory
            Get-ScheduledTaskInfo -TaskName $taskName | Select-Object LastRunTime, LastTaskResult, NextRunTime
        }
        & $pythonPath $entryPath status
    }
    'Disable' {
        if ($null -eq (Get-OwnedTask)) { throw 'Startup task is not installed.' }
        Disable-ScheduledTask -TaskName $taskName | Out-Null
        & $pythonPath $entryPath stop
        if ($LASTEXITCODE -ne 0) { throw 'Task disabled, but graceful stop failed. Inspect the log.' }
        Write-Output 'Login startup disabled; automation stopped.'
    }
    'Uninstall' {
        $task = Get-OwnedTask
        if ($null -ne $task) {
            Disable-ScheduledTask -TaskName $taskName | Out-Null
        }
        & $pythonPath $entryPath stop
        if ($LASTEXITCODE -ne 0) { throw 'Stop failed; task was not removed. Inspect the log.' }
        if ($null -ne $task) { Unregister-ScheduledTask -TaskName $taskName -Confirm:$false }
        Write-Output 'Startup task removed. Configuration, screenshots and history retained.'
    }
}
