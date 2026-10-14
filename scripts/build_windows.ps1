<#
.SYNOPSIS
    Builds the standalone Excel ID Card Generator Windows application using PyInstaller.
.DESCRIPTION
    Creates a clean virtual environment, installs dependencies, executes PyInstaller,
    and produces the standalone x64 release folder in dist/ExcelIDCardGenerator.
#>

$ErrorActionPreference = "Stop"

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  Building Excel ID Card Generator for Windows x64" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# Ensure in root directory
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RootDir = Split-Path -Parent $ScriptDir
Set-Location $RootDir

# 1. Clean previous builds
Write-Host "`n[1/4] Cleaning previous build artifacts..." -ForegroundColor Yellow
if (Test-Path "build") { Remove-Item -Recurse -Force "build" }
if (Test-Path "dist\ExcelIDCardGenerator") { Remove-Item -Recurse -Force "dist\ExcelIDCardGenerator" }

# 2. Check Python / Virtualenv
Write-Host "`n[2/4] Verifying Python environment..." -ForegroundColor Yellow
python --version

# 3. Install requirements
Write-Host "`n[3/4] Ensuring build dependencies are installed..." -ForegroundColor Yellow
pip install -r requirements.txt
pip install -e .

# 4. Run PyInstaller
Write-Host "`n[4/4] Executing PyInstaller package build..." -ForegroundColor Yellow
pyinstaller --clean packaging\id_card_generator.spec

if (Test-Path "dist\ExcelIDCardGenerator\ExcelIDCardGenerator.exe") {
    Write-Host "`n==========================================================" -ForegroundColor Green
    Write-Host "  BUILD SUCCESSFUL!" -ForegroundColor Green
    Write-Host "  Standalone executable created at:" -ForegroundColor Green
    Write-Host "  dist\ExcelIDCardGenerator\ExcelIDCardGenerator.exe" -ForegroundColor Green
    Write-Host "==========================================================" -ForegroundColor Green
} else {
    Write-Error "Build finished but executable was not found."
}
