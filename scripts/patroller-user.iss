; 巡查者 (Patroller) - User-Level Installer (no admin required)
; Inno Setup Script - Supports English & Simplified Chinese

#define MyAppName "巡查者 (Patroller)"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Patroller"
#define MyAppURL "https://github.com/Hlz-H/-patroller"

[Setup]
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567893}
AppName={cm:PatrollerAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={localappdata}\Patroller
DefaultGroupName=巡查者 (Patroller)
DisableProgramGroupPage=yes
OutputDir=..\dist-installers
OutputBaseFilename=Patroller-User-Setup-{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=none
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
Source: "..\backend\dist\*.js"; DestDir: "{app}\Backend\dist"; Components: backend; Flags: ignoreversion
Source: "..\backend\dist\node.exe"; DestDir: "{app}\Backend"; Components: backend; Flags: ignoreversion
Source: "..\backend\dist\sql-wasm.wasm"; DestDir: "{app}\Backend\dist"; Components: backend; Flags: ignoreversion
Source: "..\backend\start-backend.bat"; DestDir: "{app}\Backend"; Components: backend; Flags: ignoreversion

; Commander NSIS installer (extracted on demand)
Source: "..\commander\release\巡查者 Setup 1.0.0.exe"; DestDir: "{tmp}"; Components: commander; Flags: ignoreversion deleteafterinstall

[Dirs]
Name: "{app}\Agent\data"; Permissions: users-modify; Components: agent
Name: "{app}\Agent\logs"; Permissions: users-modify; Components: agent
Name: "{app}\Backend\data"; Permissions: users-modify; Components: backend
Name: "{app}\Backend\logs"; Permissions: users-modify; Components: backend

[Tasks]
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
