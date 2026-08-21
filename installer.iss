#define MyAppName "YT Video Developer"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Ghayathri Malcolm"
#define MyAppExeName "YTVideoDeveloper.exe"

[Setup]
AppId={{5D281800-2367-4CF6-8750-2862DDEA1FBA}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
; Installs per-user, no admin rights required.
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=installer_output
OutputBaseFilename=YTVideoDeveloper-Setup-{#MyAppVersion}
SetupIconFile=assets\app_icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
Source: "dist\YTVideoDeveloper\*"; DestDir: "{app}"; Excludes: "app.log,.env"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Remove the app.log we write next to the exe; user data in %LOCALAPPDATA%\YTVideoDeveloper
; (.env, projects\) is deliberately left alone so uninstall/reinstall never loses projects.
Type: files; Name: "{app}\app.log"
