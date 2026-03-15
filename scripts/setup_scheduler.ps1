# Setup Windows Task Scheduler for daily property search at 7:00 AM
# Run this script once as Administrator to register the task

$TaskName = "PropertySearch_DailyRun"
$Python = "C:\Users\liam.bond\AppData\Local\Programs\Python\Python313\python.exe"
$ProjectDir = "C:\Users\liam.bond\Documents\Property Search Tool"
$LogDir = Join-Path $ProjectDir "output\logs"

# Create log directory if it doesn't exist
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

# Build the action (run python -m src run, log output)
$LogFile = Join-Path $LogDir "scheduler.log"
$Action = New-ScheduledTaskAction `
    -Execute $Python `
    -Argument "-m src run" `
    -WorkingDirectory $ProjectDir

# Run daily at 7:00 AM
$Trigger = New-ScheduledTaskTrigger -Daily -At "7:00AM"

# Run whether or not user is logged on, with highest privileges
$Settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2) `
    -RestartCount 1 `
    -RestartInterval (New-TimeSpan -Minutes 10) `
    -StartWhenAvailable

$Principal = New-ScheduledTaskPrincipal `
    -UserId $env:USERNAME `
    -LogonType Interactive `
    -RunLevel Limited

# Remove existing task if present
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

# Register the task
Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Principal $Principal `
    -Description "Daily property search: scrapes Rightmove, fetches details, enriches, and generates HTML report at 7AM"

Write-Host ""
Write-Host "Task '$TaskName' registered successfully." -ForegroundColor Green
Write-Host "It will run daily at 7:00 AM."
Write-Host ""
Write-Host "To verify: Get-ScheduledTask -TaskName '$TaskName'"
Write-Host "To run now: Start-ScheduledTask -TaskName '$TaskName'"
Write-Host "To remove:  Unregister-ScheduledTask -TaskName '$TaskName'"
