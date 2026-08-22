param(
    [string]$Image = "sakura-executor:0.1.0"
)

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
docker build -t $Image $ScriptDir
Write-Host "Built $Image"
