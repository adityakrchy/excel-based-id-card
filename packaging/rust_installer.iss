; Inno Setup script for the native Rust release.
; Build the executable first with the stable MSVC target:
; cargo build --release --target x86_64-pc-windows-msvc

#define MyAppName "Excel ID Card Generator"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "CardForge"
#define MyAppExeName "excel-id-card-rust.exe"

[Setup]
AppId={{B7B2F1C8-2D1F-4F0B-9A2B-7C1A6C2E4B10}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
VersionInfoVersion={#MyAppVersion}
VersionInfoProductName={#MyAppName}
VersionInfoDescription={#MyAppName} native Windows application
VersionInfoCompany={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
OutputDir=..\dist\rust-installer
OutputBaseFilename=ExcelIDCardGenerator-Rust-{#MyAppVersion}-Setup
Compression=lzma
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64
PrivilegesRequired=lowest
WizardStyle=modern
UninstallDisplayIcon={app}\{#MyAppExeName}

[Files]
Source: "..\target\x86_64-pc-windows-msvc\release\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion

; Project files use the existing .json format.  Registering every .json file
; would claim unrelated user documents, so no broad file association is added.

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Dirs]
; User projects, caches, logs, and photo indexes are intentionally not removed
; by the installer. The application owns those locations at runtime.
