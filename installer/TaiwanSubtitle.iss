#define MyAppName "Taiwan Subtitle"
#define MyAppVersion "0.5.0"
#define MyAppPublisher "Taiwan Subtitle"
#define MyAppExeName "TaiwanSubtitle.exe"

[Setup]
AppId={B8A842F8-A06C-4B9C-A9A8-7A9E7B6C0C30}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\TaiwanSubtitle
DefaultGroupName={#MyAppName}
OutputDir=..\release
OutputBaseFilename=TaiwanSubtitle-windows-x64-setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
UninstallDisplayIcon={app}\{#MyAppExeName}

[Files]
Source: "..\dist\TaiwanSubtitle\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Taiwan Subtitle"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\Taiwan Subtitle"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "建立桌面捷徑"; Flags: unchecked

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "啟動 Taiwan Subtitle"; Flags: nowait postinstall skipifsilent
