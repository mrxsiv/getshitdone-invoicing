; Inno Setup script for GET SHIT DONE
; Build with: "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" packaging\installer.iss
; (packaging\build.ps1 runs PyInstaller + bundles Chromium + this script.)

#define AppName "GET SHIT DONE"
#define AppVersion "1.02"
#define AppPublisher "Paul Manson"
#define AppExe "GETSHITDONE.exe"

[Setup]
AppId={{A7E3F2C1-9B4D-4E6A-8C2F-1A2B3C4D5E6F}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={sd}\GSD
DisableProgramGroupPage=yes
DisableDirPage=no
UsePreviousAppDir=yes
CloseApplications=yes
RestartApplications=no
OutputDir=Output
OutputBaseFilename=GETSHITDONE-Setup-{#AppVersion}
SetupIconFile=GSD.ico
UninstallDisplayIcon={app}\GSD.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin

[Files]
Source: "..\dist\GETSHITDONE\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "GSD.ico"; DestDir: "{app}"; Flags: ignoreversion

[Tasks]
Name: "desktopicon";  Description: "Create a &Desktop shortcut";    GroupDescription: "Shortcuts:"
Name: "startmenuicon"; Description: "Create a &Start Menu shortcut"; GroupDescription: "Shortcuts:"
Name: "taskbaricon";  Description: "Pin to the &Taskbar (if supported by Windows)"; GroupDescription: "Shortcuts:"; Flags: unchecked

[Icons]
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; IconFilename: "{app}\GSD.ico"; Tasks: desktopicon
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"; IconFilename: "{app}\GSD.ico"; Tasks: startmenuicon
Name: "{userappdata}\Microsoft\Internet Explorer\Quick Launch\User Pinned\TaskBar\{#AppName}"; Filename: "{app}\{#AppExe}"; IconFilename: "{app}\GSD.ico"; Tasks: taskbaricon

[Run]
Filename: "{app}\{#AppExe}"; Description: "Launch {#AppName} now"; Flags: nowait postinstall skipifsilent

[Code]
var
  DataDirPage: TInputDirWizardPage;
  IsUpgrade: Boolean;

function PrevInstalled(): Boolean;
var
  s: String;
begin
  Result :=
    RegQueryStringValue(HKLM, 'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\{A7E3F2C1-9B4D-4E6A-8C2F-1A2B3C4D5E6F}_is1', 'UninstallString', s) or
    RegQueryStringValue(HKCU, 'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\{A7E3F2C1-9B4D-4E6A-8C2F-1A2B3C4D5E6F}_is1', 'UninstallString', s);
end;

procedure InitializeWizard;
begin
  IsUpgrade := PrevInstalled();
  DataDirPage := CreateInputDirPage(wpSelectDir,
    'Select data location',
    'Where should your invoices and database be stored?',
    'Your data (database, invoice PDFs, exports and backups) will be kept here.' + #13#10 +
    'Tip: choose a Google Drive or OneDrive folder so it is backed up to the cloud.',
    False, '');
  DataDirPage.Add('Data folder');
  DataDirPage.Values[0] := ExpandConstant('{sd}\GSD\data');
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := False;
  // On an upgrade, reuse the existing install folder, data location and
  // shortcuts. Don't re-prompt — re-choosing the data folder could point the
  // app at the wrong place and "lose" the user's data.
  if IsUpgrade then
    if (PageID = wpSelectDir) or (PageID = wpSelectTasks) or (PageID = DataDirPage.ID) then
      Result := True;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  dataDir: String;
begin
  if CurStep = ssPostInstall then
  begin
    if not IsUpgrade then
    begin
      // Fresh install only: record the chosen data folder for the app to read.
      dataDir := DataDirPage.Values[0];
      ForceDirectories(dataDir);
      SaveStringToFile(ExpandConstant('{app}\data_location.txt'), dataDir, False);
    end;
    // Upgrade: leave the existing {app}\data_location.txt untouched.
  end;
end;
