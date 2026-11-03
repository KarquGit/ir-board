#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#ifndef AppDisplayVersion
  #define AppDisplayVersion "1.0.0"
#endif
[Setup]
AppId={{20B1162B-0C3B-4C4B-84A6-E24D708B0333}
AppName=iR-Board
AppVersion={#AppDisplayVersion}
AppVerName=iR-Board {#AppDisplayVersion}
AppPublisher=iR-Board contributors
VersionInfoDescription=iR-Board local dashboard installer
VersionInfoProductName=iR-Board
VersionInfoVersion={#AppVersion}
VersionInfoCopyright=Copyright 2026 iR-Board contributors
DefaultDirName={localappdata}\Programs\iR-Board
DefaultGroupName=iR-Board
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist\installer
OutputBaseFilename=iR-Board-Setup-{#AppVersion}-windows-x64
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupIconFile=..\irboard\static\icon.ico
LicenseFile=..\LICENSE
UninstallDisplayIcon={app}\iR-Board.exe
CloseApplications=yes
[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked
; User appearance lives in {localappdata}\iR-Board\layout.json, outside {app}.
; Updates must preserve that directory and this stable AppId.
[Files]
Source: "..\dist\iR-Board\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
[Icons]
Name: "{group}\iR-Board"; Filename: "{app}\iR-Board.exe"
Name: "{autodesktop}\iR-Board"; Filename: "{app}\iR-Board.exe"; Tasks: desktopicon
[InstallDelete]
Type: files; Name: "{group}\iR-Board Demo.lnk"
[Run]
Filename: "{app}\iR-Board.exe"; Description: "Launch iR-Board and show the tablet QR code"; Flags: nowait postinstall skipifsilent
