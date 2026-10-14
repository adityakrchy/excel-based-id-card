<#
.SYNOPSIS
    Cleans all temporary build, packaging, cache, and test artifacts.
#>

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RootDir = Split-Path -Parent $ScriptDir
Set-Location $RootDir

Write-Host "Cleaning build and cache directories..." -ForegroundColor Yellow

$DirsToClean = @(
    "build",
    "dist",
    ".pytest_cache",
    ".eggs",
    "*.egg-info"
)

foreach ($dir in $DirsToClean) {
    if (Test-Path $dir) {
        Remove-Item -Recurse -Force $dir
        Write-Host "Removed $dir" -ForegroundColor Green
    }
}

Get-ChildItem -Path . -Include "__pycache__", "*.pyc" -Recurse -Force | Remove-Item -Recurse -Force
Write-Host "All caches and build artifacts cleaned successfully." -ForegroundColor Green
