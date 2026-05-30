; 巡查者 (Patroller) - All-in-One Installer
; Inno Setup Script - Supports English & Simplified Chinese

#define MyAppName "巡查者 (Patroller)"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Patroller"
#define MyAppURL "https://github.com/patroller"

[Setup]
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567892}
AppName={cm:PatrollerAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\Patroller
DefaultGroupName=巡查者 (Patroller)
DisableProgramGroupPage=yes
OutputDir=..\dist-installers
OutputBaseFilename=Patroller-Setup-{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
LanguageDetectionMethod=uilanguage
ShowLanguageDialog=auto

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"
Name: "zh"; MessagesFile: "..\scripts\ChineseSimplified.isl"

[Components]
Name: "agent"; Description: "{cm:AgentDescription}"; Types: full custom; Flags: fixed
Name: "backend"; Description: "{cm:BackendDescription}"; Types: full custom
Name: "commander"; Description: "{cm:CommanderDescription}"; Types: full custom

[Types]
Name: "full"; Description: "Full installation"
Name: "custom"; Description: "Custom installation"; Flags: iscustom

[Files]
; Agent files
Source: "..\agent\dist\patroller-agent.exe"; DestDir: "{app}\Agent"; Components: agent; Flags: ignoreversion
Source: "..\agent\agent\config.yaml"; DestDir: "{app}\Agent"; Components: agent; Flags: ignoreversion
Source: "..\agent\rules\*.yar"; DestDir: "{app}\Agent\rules"; Components: agent; Flags: ignoreversion

; Backend files
Source: "..\backend\dist\node.exe"; DestDir: "{app}\Backend"; Components: backend; Flags: ignoreversion
Source: "..\backend\dist\*.js"; DestDir: "{app}\Backend\dist"; Components: backend; Flags: ignoreversion
Source: "..\backend\dist\*.wasm"; DestDir: "{app}\Backend\dist"; Components: backend; Flags: ignoreversion
Source: "..\backend\start-backend.bat"; DestDir: "{app}\Backend"; Components: backend; Flags: ignoreversion

; Commander NSIS installer (extracted on demand)
Source: "..\commander\release\巡查者 Setup 1.0.0.exe"; DestDir: "{tmp}"; Components: commander; Flags: ignoreversion deleteafterinstall

[Dirs]
Name: "{app}\Agent\data"; Permissions: users-modify; Components: agent
Name: "{app}\Agent\logs"; Permissions: users-modify; Components: agent
Name: "{app}\Backend\data"; Permissions: users-modify; Components: backend
Name: "{app}\Backend\logs"; Permissions: users-modify; Components: backend

[Tasks]
Name: "agent_service"; Description: "{cm:ServiceInstallDesc}"; Components: agent; GroupDescription: "{cm:AdditionalIcons}"
Name: "agent_desktop"; Description: "{cm:CreateDesktopIcon}"; Components: agent; GroupDescription: "{cm:AdditionalIcons}"; Flags: checkedonce
Name: "backend_desktop"; Description: "{cm:CreateDesktopIcon}"; Components: backend; GroupDescription: "{cm:AdditionalIcons}"; Flags: checkedonce
Name: "commander_desktop"; Description: "{cm:CreateDesktopIcon}"; Components: commander; GroupDescription: "{cm:AdditionalIcons}"; Flags: checkedonce

[Icons]
Name: "{group}\{cm:PatrollerAgentName}"; Filename: "{app}\Agent\patroller-agent.exe"; Components: agent
Name: "{group}\{cm:PatrollerBackendName}"; Filename: "{app}\Backend\start-backend.bat"; Components: backend
Name: "{group}\{cm:PatrollerCommanderName}"; Filename: "{app}\Commander\巡查者.exe"; Components: commander
Name: "{autodesktop}\{cm:PatrollerAgentName}"; Filename: "{app}\Agent\patroller-agent.exe"; Components: agent; Tasks: agent_desktop
Name: "{autodesktop}\{cm:PatrollerBackendName}"; Filename: "{app}\Backend\start-backend.bat"; Components: backend; Tasks: backend_desktop
Name: "{autodesktop}\{cm:PatrollerCommanderName}"; Filename: "{app}\Commander\巡查者.exe"; Components: commander; Tasks: commander_desktop
Name: "{group}\{cm:UninstallProgram,{cm:PatrollerAppName}}"; Filename: "{uninstallexe}"

[Run]
Filename: "{app}\Agent\patroller-agent.exe"; Components: agent; Description: "{cm:LaunchProgram,{cm:PatrollerAgentName}}"; Flags: nowait postinstall skipifsilent shellexec
Filename: "{app}\Backend\start-backend.bat"; Components: backend; Description: "{cm:LaunchProgram,{cm:PatrollerBackendName}}"; Flags: nowait postinstall skipifsilent shellexec
Filename: "{tmp}\巡查者 Setup 1.0.0.exe"; Components: commander; Description: "{cm:LaunchProgram,{cm:PatrollerCommanderName}}"; Flags: nowait postinstall skipifsilent shellexec

[UninstallRun]
Filename: "taskkill"; Parameters: "/f /im patroller-agent.exe"; Flags: runhidden
Filename: "taskkill"; Parameters: "/f /im node.exe"; Flags: runhidden

[Code]
procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
begin
  if CurStep = ssPostInstall then
  begin
    if IsComponentSelected('agent') then
    begin
      Exec('netsh', 'advfirewall firewall add rule name="巡查者 Agent" dir=in action=allow program="' + ExpandConstant('{app}') + '\Agent\patroller-agent.exe" enable=yes', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    end;
    if IsComponentSelected('backend') then
    begin
      Exec('netsh', 'advfirewall firewall add rule name="巡查者 Backend" dir=in action=allow program="' + ExpandConstant('{app}') + '\Backend\node.exe" enable=yes', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    end;
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  ResultCode: Integer;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    Exec('netsh', 'advfirewall firewall delete rule name="巡查者 Agent"', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    Exec('netsh', 'advfirewall firewall delete rule name="巡查者 Backend"', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  end;
end;
