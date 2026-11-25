param([switch]$Remove)
$ErrorActionPreference = 'Stop'
$project = (Resolve-Path -LiteralPath (Split-Path -Parent $PSScriptRoot)).Path
$taskName = 'LocalMarketingEngine'
if ($Remove) {
  Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
  exit
}
$pythonExe = Join-Path $project '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonExe)) { throw 'Run setup.ps1 first' }
# Run every five minutes under the signed-in user. The engine applies Copenhagen time and daily idempotency.
$action = New-ScheduledTaskAction -Execute $pythonExe -Argument '-m engine.cli tick' -WorkingDirectory $project
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 5)
$options = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 2) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$principal = New-ScheduledTaskPrincipal -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $options -Principal $principal -Description 'Local marketing pipeline; paid APIs not required' -Force
Get-ScheduledTask -TaskName $taskName | Select-Object TaskName,State
