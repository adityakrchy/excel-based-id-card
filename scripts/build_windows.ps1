name: Build Windows Application

on:
  push:
    branches: [main, master]
  pull_request:
    branches: [main, master]
  workflow_dispatch:

jobs:
  build-windows:
    runs-on: windows-latest

    steps:
      # 1. Check out the repository
      - name: Check out repository
        uses: actions/checkout@v4

      # 2. Set up Python
      - name: Set up Python 3.12
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: "pip"

      # 3. Install Python dependencies
      - name: Install dependencies
        shell: pwsh
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt
          pip install -e .

      # 4. Run tests
      - name: Run automated test suite
        shell: pwsh
        run: |
          pytest tests/
          if ($LASTEXITCODE -ne 0) {
            throw "Automated tests failed."
          }

      # 5. Build the standalone application
      - name: Build standalone executable with PyInstaller
        shell: pwsh
        run: |
          pyinstaller --clean packaging/id_card_generator.spec
          if ($LASTEXITCODE -ne 0) {
            throw "PyInstaller build failed."
          }

      # 6. Verify the executable
      - name: Verify executable creation
        shell: pwsh
        run: |
          $exe = "dist\ExcelIDCardGenerator\ExcelIDCardGenerator.exe"

          if (-not (Test-Path $exe)) {
            Write-Error "ExcelIDCardGenerator.exe was not found at $exe"
            Get-ChildItem dist -Recurse -ErrorAction SilentlyContinue
            exit 1
          }

          Write-Host "Executable verified successfully." -ForegroundColor Green

      # 7. Create the standalone ZIP package
      - name: Zip standalone application
        shell: pwsh
        run: |
          $source = "dist\ExcelIDCardGenerator"
          $destination = "dist\ExcelIDCardGenerator-Windows-x64.zip"

          if (-not (Test-Path $source)) {
            throw "Application directory not found: $source"
          }

          Compress-Archive `
            -Path "$source\*" `
            -DestinationPath $destination `
            -Force

          if (-not (Test-Path $destination)) {
            throw "Standalone ZIP was not created."
          }

          Write-Host "Standalone ZIP created successfully." -ForegroundColor Green

      # 8. Install Inno Setup
      - name: Install Inno Setup
        shell: pwsh
        run: |
          choco install innosetup -y --no-progress

          if ($LASTEXITCODE -ne 0) {
            throw "Failed to install Inno Setup."
          }

      # 9. Compile the installer
      - name: Build Inno Setup Installer
        shell: pwsh
        run: |
          $iscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"

          if (-not (Test-Path $iscc)) {
            throw "Inno Setup compiler not found: $iscc"
          }

          if (-not (Test-Path "packaging\installer.iss")) {
            throw "Installer script not found: packaging\installer.iss"
          }

          New-Item -ItemType Directory -Path "dist\installer" -Force | Out-Null

          & $iscc /O"dist\installer" /F"ExcelIDCardGenerator-Setup" "packaging\installer.iss"

          if ($LASTEXITCODE -ne 0) {
            throw "Inno Setup compilation failed."
          }

          $installer = "dist\installer\ExcelIDCardGenerator-Setup.exe"

          if (-not (Test-Path $installer)) {
            throw "Installer executable was not created at $installer"
          }

          Write-Host "Installer created successfully." -ForegroundColor Green

      # 10. Upload the standalone ZIP
      - name: Upload Windows Standalone ZIP Artifact
        uses: actions/upload-artifact@v4
        with:
          name: ExcelIDCardGenerator-Windows-x64
          path: dist/ExcelIDCardGenerator-Windows-x64.zip
          if-no-files-found: error
          retention-days: 14

      # 11. Upload the installer
      - name: Upload Windows Installer
        uses: actions/upload-artifact@v4
        with:
          name: ExcelIDCardGenerator-Installer
          path: dist/installer/ExcelIDCardGenerator-Setup.exe
          if-no-files-found: error
          retention-days: 14
