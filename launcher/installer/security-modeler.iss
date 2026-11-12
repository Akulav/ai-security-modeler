; Security Modeler's Windows setup (Inno Setup 6), the same kind as Akulav's other apps: Welcome, License, Folder,
; Shortcuts, Install, Finish (with "Launch Security Modeler"); per user, no administrator rights; an uninstaller in
; Settings -> Apps and the Start menu. The release workflow builds it:
;
;   iscc /DAppVersion=0.2.0 /DExe=<path>\SecurityModeler.exe /O<out dir> launcher\installer\security-modeler.iss
;
; This one file both installs and updates: it's the only Windows file of a release. The launcher's update
; (launcher/src/update.rs) downloads it and starts it on the install's folder:
;
;   SecurityModeler-Setup.exe /SILENT /SUPPRESSMSGBOXES /NORESTART /UPDATE /DIR=<folder> /LOG=<file>
;
; The program unpacks the app and sets up Python on its first start; your map, settings and the LLM runtime live in
; the same folder and are never touched by an update. Pictures and the icon come from launcher/assets
; (python tools_dev/make_icons.py).

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef Exe
  #define Exe "..\target\release\SecurityModeler.exe"
#endif

#define AppName "Security Modeler"
#define AppExe "SecurityModeler.exe"

[Setup]
; (never change the AppId: it's how an update and the uninstaller find this install)
AppId={{3C8E5A71-2F4B-4D9E-8A1C-6B7D9E0F2A43}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Akulav
AppCopyright=Made by Akulav
AppPublisherURL=https://github.com/Akulav/ai-security-modeler
AppSupportURL=https://github.com/Akulav/ai-security-modeler/issues
AppUpdatesURL=https://github.com/Akulav/ai-security-modeler/releases
VersionInfoVersion={#AppVersion}
VersionInfoCompany=Akulav
VersionInfoCopyright=Made by Akulav
VersionInfoDescription={#AppName} Setup
VersionInfoProductName={#AppName}
; (the folder launchers before 0.2 already used: their map and settings are found where they are)
DefaultDirName={localappdata}\SecurityModeler
DisableWelcomePage=no
DisableDirPage=auto
DisableProgramGroupPage=yes
UsePreviousAppDir=yes
DirExistsWarning=no
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
LicenseFile=..\..\LICENSE
OutputBaseFilename=SecurityModeler-Setup
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
WizardStyle=modern
WizardImageFile=..\assets\wizard-large.bmp,..\assets\wizard-large-200.bmp
WizardSmallImageFile=..\assets\wizard-small.bmp,..\assets\wizard-small-200.bmp
Compression=lzma2/max
SolidCompression=yes
CloseApplications=force
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
english.DataNote=Your map, settings and the local LLM (about 18 GB once downloaded) will be stored in this folder too.

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "{#Exe}"; DestDir: "{app}"; DestName: "{#AppExe}"; Flags: ignoreversion
Source: "..\..\LICENSE"; DestDir: "{app}"; DestName: "LICENSE.txt"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"; Comment: "Map your accounts and devices - made by Akulav"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"; Comment: "Map your accounts and devices - made by Akulav"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; WorkingDir: "{app}"; Flags: nowait postinstall skipifsilent
; (an update from the launcher: start the new version - it waits for the old one to let go of the folder)
Filename: "{app}\{#AppExe}"; Parameters: "--updated"; WorkingDir: "{app}"; Flags: nowait; Check: IsUpdate

[UninstallDelete]
Type: files; Name: "{app}\{#AppExe}.old"
Type: files; Name: "{app}\{#AppExe}.new"
Type: files; Name: "{app}\update.json"
Type: filesandordirs; Name: "{app}\cache\update"

[Code]
function IsUpdate(): Boolean;
var
  I: Integer;
begin
  Result := False;
  for I := 1 to ParamCount do
    if CompareText(ParamStr(I), '/UPDATE') = 0 then
      Result := True;
end;

// A running Security Modeler from this folder is ended first (it takes the app and its LLM with it).
procedure StopRunning();
var
  Code: Integer;
begin
  Exec('powershell.exe',
       '-NoProfile -NonInteractive -Command "Get-Process SecurityModeler -ErrorAction SilentlyContinue | ' +
       'Where-Object { $_.Path -eq ''' + ExpandConstant('{app}') + '\{#AppExe}'' } | Stop-Process -Force"',
       '', SW_HIDE, ewWaitUntilTerminated, Code);
  Sleep(1000);
end;

procedure InitializeWizard();
begin
  WizardForm.SelectDirLabel.Caption := WizardForm.SelectDirLabel.Caption + #13#10 + CustomMessage('DataNote');
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Result := '';
  StopRunning();
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usUninstall then
    StopRunning();
  // (never asked when silent: then the data always stays)
  if (CurUninstallStep = usPostUninstall) and not UninstallSilent then
  begin
    if MsgBox('Security Modeler is uninstalled.' + #13#10#13#10 +
              'Also delete its folder ' + ExpandConstant('{app}') + ' ?' + #13#10 +
              'That deletes your map, settings and the downloaded LLM for good.' + #13#10#13#10 +
              'No keeps them: installing Security Modeler again brings everything back.',
              mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
      DelTree(ExpandConstant('{app}'), True, True, True);
  end;
end;
