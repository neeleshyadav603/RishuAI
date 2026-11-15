; Inno Setup script for Rishu (per-user install, no admin rights needed).
; Built on GitHub Actions: ISCC /DAppVersion=x.y.z installer\rishu.iss

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{6E2B6C1E-7B1B-4F0E-9B55-5A1C0D5E7A11}
AppName=Rishu
AppVersion={#AppVersion}
AppPublisher=Rishu
DefaultDirName={localappdata}\Programs\Rishu
DefaultGroupName=Rishu
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist-installer
OutputBaseFilename=RishuSetup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayName=Rishu

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Files]
Source: "..\app\build\windows\x64\runner\Release\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion
Source: "..\dist\rishu-core\*"; DestDir: "{app}\core"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\Rishu"; Filename: "{app}\rishu.exe"
Name: "{autodesktop}\Rishu"; Filename: "{app}\rishu.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\rishu.exe"; Description: "Start Rishu"; Flags: nowait postinstall skipifsilent
