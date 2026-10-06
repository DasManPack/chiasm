#define MyAppName "Chiasm"
#define MyAppVersion "0.1.2"
#define MyAppPublisher "Chiasm contributors"
#define MyAppExeName "Chiasm.exe"

[Setup]
AppId={{9F4DD1D7-5318-4A74-91FB-3EE43A8D6407}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\Chiasm
DefaultGroupName=Chiasm
OutputDir=dist
OutputBaseFilename=Chiasm-Windows-x64-Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Files]
Source: "dist\Chiasm\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Chiasm"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\Chiasm"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"; Flags: unchecked

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch Chiasm"; Flags: nowait postinstall skipifsilent
