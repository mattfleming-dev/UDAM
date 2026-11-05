; Inno Setup script for Universal Stock DAM.
;
; Packages the PyInstaller onedir build (dist\windows\UniversalStockDAM) into a
; Windows installer. Model weight files (*.gguf) are intentionally excluded so
; the installer stays a manageable size -- users supply their own model(s) by
; dropping .gguf files into the "models" folder created under
; %LOCALAPPDATA%\UniversalStockDAM after install (also reachable from
; Settings > "Open Models Folder" inside the app).
;
; Build with build_installer.ps1, which runs build_windows.ps1 -ExcludeModels
; first and then invokes ISCC.exe against this script.

#define MyAppName "Universal Stock DAM"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Universal Stock DAM"
#define MyAppExeName "UniversalStockDAM.exe"
#define MySourceDir "..\dist\windows\UniversalStockDAM"

[Setup]
AppId={{9E7E3F0E-9E3F-4C4B-9C1D-6C1B6F3B4E2A}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\dist\installer
OutputBaseFilename=UniversalStockDAM-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#MyAppExeName}
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
Source: "{#MySourceDir}\*"; DestDir: "{app}"; Excludes: "*.gguf"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[Code]
procedure InitializeWizard();
begin
  WizardForm.WelcomeLabel2.Caption :=
    WizardForm.WelcomeLabel2.Caption + #13#10#13#10 +
    'Note: This installer does not include AI model files. After installing, ' +
    'open the app and use Settings > "Open Models Folder" to add your own ' +
    '.gguf model (and optional mmproj vision file) for AI-assisted metadata.';
end;
