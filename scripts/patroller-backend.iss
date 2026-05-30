; 巡查者 Backend Installer
; Inno Setup Script - Supports English & Simplified Chinese

#define MyAppName "巡查者 Backend"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Patroller"
#define MyAppURL "https://github.com/patroller"

[Setup]
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567891}
AppName={cm:PatrollerBackendName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\Patroller\Backend
DefaultGroupName=巡查者 (Patroller)
DisableProgramGroupPage=yes
OutputDir=..\dist-installers
OutputBaseFilename=Patroller-Backend-Setup-{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
LanguageDetectionMethod=uilanguage
ShowLanguageDialog=auto

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"
Name: "zh"; MessagesFile: "..\scripts\ChineseSimplified.isl"

[Files]
Source: "..\backend\dist\node.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\backend\dist\*.js"; DestDir: "{app}\dist"; Flags: ignoreversion
Source: "..\backend\dist\*.wasm"; DestDir: "{app}\dist"; Flags: ignoreversion
Source: "..\backend\start-backend.bat"; DestDir: "{app}"; Flags: ignoreversion

[Dirs]
Name: "{app}\data"; Permissions: users-modify
Name: "{app}\logs"; Permissions: users-modify

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "startup"; Description: "{cm:AutoStartProgram,{cm:PatrollerBackendName}}"; GroupDescription: "{cm:AdditionalIcons}"

[Icons]
Name: "{group}\{cm:PatrollerBackendName}"; Filename: "{app}\start-backend.bat"
Name: "{group}\{cm:UninstallProgram,{cm:PatrollerBackendName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{cm:PatrollerBackendName}"; Filename: "{app}\start-backend.bat"; Tasks: desktopicon

[Run]
Filename: "{app}\start-backend.bat"; Description: "{cm:LaunchProgram,{cm:PatrollerBackendName}}"; Flags: nowait postinstall skipifsilent shellexec

[UninstallRun]
Filename: "taskkill"; Parameters: "/f /im node.exe"; Flags: runhidden

[Code]
var
  ServicePage: TInputOptionWizardPage;

procedure InitializeWizard;
begin
  ServicePage := CreateInputOptionPage(wpSelectTasks,
    SetupMessage(msgWizardSelectComponents),
    SetupMessage(msgSelectComponentsDesc),
    '',
    True, False);
  ServicePage.Add('{cm:ConfigFirewallDesc}');
  ServicePage.Values[0] := True;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
begin
  if CurStep = ssPostInstall then
  begin
    Exec('netsh', 'advfirewall firewall add rule name="巡查者 Backend" dir=in action=allow program="' + ExpandConstant('{app}') + '\node.exe" enable=yes', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  ResultCode: Integer;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    Exec('netsh', 'advfirewall firewall delete rule name="巡查者 Backend"', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  end;
end;
