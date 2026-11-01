; ============================================================
;  SWIM-AI - Inno Setup script (single-file Windows installer)
;  Build:  iscc packaging\installer.iss
;  Output: dist\SWIM-AI-Setup.exe
;  Requires Inno Setup 6:  https://jrsoftware.org/isdl.php
; ============================================================
#define MyAppName "SWIM-AI"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "SWIM-AI"
#define MyAppExeName "SWIM-AI.exe"

[Setup]
AppId={{8A2F4C1E-2B77-4C2B-9E4A-1F0C7B3D5E11}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
; 64-bit only build target
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; ~500 MB of files: LZMA2 compresses best, solid mode keeps the setup small
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
OutputDir=..\dist
OutputBaseFilename=SWIM-AI-Setup
SetupIconFile=swim_ai.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
; the app writes nothing into its own folder, so a normal user install is fine
PrivilegesRequiredOverridesAllowed=dialog
MinVersion=10.0

[Languages]
Name: "farsi"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "ساخت آیکون روی دسکتاپ"; GroupDescription: "میان‌بر"

[Files]
Source: "..\dist\SWIM-AI\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\SWIM-AI"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\SWIM-AI"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "اجرای SWIM-AI"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; keep the downloaded pose models (%LOCALAPPDATA%\SWIM-AI\models) so a
; re-install does not have to fetch them again - remove only the logs.
Type: files; Name: "{localappdata}\SWIM-AI\crash_log.txt"
Type: files; Name: "{localappdata}\SWIM-AI\console.log"
