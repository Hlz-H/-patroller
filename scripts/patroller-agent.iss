; 巡查者 Agent Installer
; Inno Setup Script - Supports English & Simplified Chinese

#define MyAppName "巡查者 Agent"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Patroller"
#define MyAppURL "https://github.com/patroller"
#define MyAppExeName "patroller-agent.exe"

[Setup]
AppId={{B2A1C3D4-E5F6-7890-ABCD-EF1234567890}
AppName={cm:PatrollerAgentName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\Patroller\Agent
DefaultGroupName=巡查者 (Patroller)
DisableProgramGroupPage=yes
OutputDir=..\dist-installers
OutputBaseFilename=Patroller-Agent-Setup-{#MyAppVersion}
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
Source: "..\agent\dist\patroller-agent.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\agent\agent\config.yaml"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\agent\rules\*.yar"; DestDir: "{app}\rules"; Flags: ignoreversion

[Dirs]
Name: "{app}\data"; Permissions: users-modify
Name: "{app}\logs"; Permissions: users-modify
Name: "{app}\rules"

[Tasks]
Name: "service"; Description: "{cm:ServiceInstall}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: checkedonce
Name: "startup"; Description: "{cm:AutoStartProgram,{cm:PatrollerAgentName}}"; GroupDescription: "{cm:AdditionalIcons}"

[Icons]
Name: "{group}\{cm:PatrollerAgentName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{cm:PatrollerAgentName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{cm:PatrollerAgentName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
Name: "{commonstartup}\{cm:PatrollerAgentName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: startup

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{cm:PatrollerAgentName}}"; Flags: nowait postinstall skipifsilent shellexec

[UninstallRun]
Filename: "taskkill"; Parameters: "/f /im patroller-agent.exe"; Flags: runhidden

[Code]
var
  ServicePage: TInputOptionWizardPage;

procedure InitializeWizard;
begin
  ServicePage := CreateInputOptionPage(wpSelectTasks,
    'Additional Options',
    'Select additional installation options.',
    'Choose which optional features to install:',
    True, False);
  ServicePage.Add('{cm:ServiceInstallDesc}');
  ServicePage.Add('{cm:ConfigFirewallDesc}');
  ServicePage.Values[0] := True;
  ServicePage.Values[1] := True;
end;

function GetServiceInstall: Boolean;
begin
  if ServicePage <> nil then
    Result := ServicePage.Values[0]
  else
    Result := True;
end;

function GetFirewallConfig: Boolean;
begin
  if ServicePage <> nil then
    Result := ServicePage.Values[1]
  else
    Result := True;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
begin
  if CurStep = ssPostInstall then
  begin
    if GetServiceInstall then
    begin
      Exec('sc', 'create PatrollerAgent binPath="' + ExpandConstant('{app}') + '\patroller-agent.exe" start=auto DisplayName="巡查者 Agent Service"', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    end;
    if GetFirewallConfig then
    begin
      Exec('netsh', 'advfirewall firewall add rule name="巡查者 Agent" dir=in action=allow program="' + ExpandConstant('{app}') + '\patroller-agent.exe" enable=yes', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    end;
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  ResultCode: Integer;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    Exec('sc', 'stop PatrollerAgent', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    Exec('sc', 'delete PatrollerAgent', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    Exec('netsh', 'advfirewall firewall delete rule name="巡查者 Agent"', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  end;
end;
