; 자동 더빙 TTS 설치 마법사 (Inno Setup 6).
; installer\build.ps1 이 PyInstaller 빌드 뒤에 /DAppVersion=<src\app_version.py 의 VERSION> 으로 컴파일한다.
#ifndef AppVersion
  #error AppVersion is not defined - run installer\build.ps1
#endif
#define AppName "자동 더빙 TTS"
#define AppExe "auto_dubbing_tts.exe"

[Setup]
AppId={{9B7E4D2A-6C15-4F8B-A3D9-2E7F1C5B8A40}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=GankWaL
AppPublisherURL=https://github.com/GankWaL/auto_dubbing_tts
; 관리자 권한 없이 현재 사용자에게 설치 → {autopf} = %LOCALAPPDATA%\Programs
; 설정(config)·.env·ocr_env·커스텀 목소리가 이 폴더에 쌓이므로 사용자 쓰기 권한이 있어야 한다
PrivilegesRequired=lowest
DefaultDirName={autopf}\AutoDubbingTTS
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\build\release
OutputBaseFilename=AutoDubbingTTS-Setup-{#AppVersion}
SetupIconFile=..\icon\icon.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\build\pyinstaller\AutoDubbingTTS\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; 별도 환경(ocr_env, tts_env)에서 소스로 실행되는 서버들
Source: "..\src\ocr.py"; DestDir: "{app}\src"; Flags: ignoreversion
Source: "..\src\ocr_easyocr.py"; DestDir: "{app}\src"; Flags: ignoreversion
Source: "..\src\ocr_server.py"; DestDir: "{app}\src"; Flags: ignoreversion
Source: "..\src\ocr_setup.py"; DestDir: "{app}\src"; Flags: ignoreversion
Source: "..\src\custom_tts_server.py"; DestDir: "{app}\src"; Flags: ignoreversion
Source: "..\src\setup_custom_tts.py"; DestDir: "{app}\src"; Flags: ignoreversion
Source: "..\bat\setup_easyocr.bat"; DestDir: "{app}\bat"; Flags: ignoreversion
Source: "..\bat\start_ocr_server.bat"; DestDir: "{app}\bat"; Flags: ignoreversion
Source: "..\bat\setup_tts_server.bat"; DestDir: "{app}\bat"; Flags: ignoreversion
Source: "..\bat\start_tts_server.bat"; DestDir: "{app}\bat"; Flags: ignoreversion
Source: "..\.env.example"; DestDir: "{app}"; Flags: ignoreversion
; 설정 파일은 처음 설치할 때만 만든다 (업데이트 때 사용자 키를 덮어쓰지 않음)
Source: "..\.env.example"; DestDir: "{app}"; DestName: ".env"; Flags: onlyifdoesntexist
Source: "..\icon\icon.ico"; DestDir: "{app}\icon"; Flags: ignoreversion
Source: "..\icon\icon.png"; DestDir: "{app}\icon"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "지금 자동 더빙 TTS 실행"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/F /IM {#AppExe}"; Flags: runhidden; RunOnceId: "StopApp"
Filename: "powershell.exe"; Parameters: "-NoProfile -Command ""Get-CimInstance Win32_Process | Where-Object {{ $_.CommandLine -like '*{app}\src\ocr_server*' -or $_.CommandLine -like '*{app}\src\custom_tts_server*' } | ForEach-Object {{ Stop-Process -Id $_.ProcessId -Force }"""; Flags: runhidden; RunOnceId: "StopServers"

[Code]
{ 실행 중인 앱을 끄고 덮어쓴다 }
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
begin
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM {#AppExe}', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Result := '';
end;

{ 설치 폴더에 쌓인 사용자 데이터는 물어보고 지운다 }
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if (CurUninstallStep = usPostUninstall) and not UninstallSilent then
    if MsgBox('설정(.env, config)·로그·EasyOCR 환경(ocr_env)·커스텀 TTS 환경(tts_env, GPT-SoVITS)·목소리 모델도 모두 삭제할까요?' + #13#10#13#10 +
              '다시 설치해서 계속 쓸 거라면 [아니요] 를 누르세요.', mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
      DelTree(ExpandConstant('{app}'), True, True, True);
end;
