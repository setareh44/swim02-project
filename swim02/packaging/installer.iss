; ============================================================
;  Setargan-Darya - Inno Setup script (single-file Windows installer)
;  Build:  iscc packaging\installer.iss
;  Output: dist\Setargan-Darya-Setup.exe
;  Requires Inno Setup 6:  https://jrsoftware.org/isdl.php
; ============================================================
#define MyAppName "Setargan-Darya"
#define MyAppVersion "2.0.0"
#define MyAppPublisher "Setareh"
#define MyAppExeName "Setargan-Darya.exe"

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
OutputBaseFilename=Setargan-Darya-Setup
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
Source: "..\dist\Setargan-Darya\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Setargan-Darya"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\Setargan-Darya"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "اجرای Setargan-Darya"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; keep the downloaded pose models (%LOCALAPPDATA%\Setargan-Darya\models) so a
; re-install does not have to fetch them again - remove only the logs.
Type: files; Name: "{localappdata}\Setargan-Darya\crash_log.txt"
Type: files; Name: "{localappdata}\Setargan-Darya\console.log"
