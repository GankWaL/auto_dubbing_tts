# auto_dubbing_tts

화면에 표시되는 대사를 읽어 **화자별 목소리로 자동 더빙**해 주는 Windows 프로그램입니다.
비주얼노벨·게임처럼 이름 박스와 대사 박스가 고정 위치에 있는 콘텐츠를 대상으로 합니다.

```text
화면 캡처(대사 영역) → 변화 감지(타자 효과가 끝날 때까지 대기) → OCR(대사·이름)
 → 화자 ↔ 목소리 매핑 → TTS 합성 → PC 스피커 재생
```

TTS 엔진은 [discord_bot_chzzk_tts](https://github.com/GankWaL/discord_bot_chzzk_tts) 의 것을 그대로 사용합니다.

## 기능

- 드래그로 **대사 영역**과 **이름 영역** 지정 (멀티 모니터 지원)
- OCR 엔진 3종 선택:
  - **Windows 내장 OCR** (기본) — 별도 설치 없음, 한국어 한 줄 15\~40ms
  - **CLOVA CRAFT + EasyOCR** — 네이버 CLOVA AI 가 공개한 CRAFT 텍스트 검출기 + EasyOCR 한국어 인식 모델. 엔진을 고르고 [시작] 하면 환경(ocr_env)이 없을 때 **바로 설치를 제안**하고 로그에 진행을 보여줌 (NVIDIA GPU 면 CUDA 약 2.5GB, 없으면 CPU 빌드 약 200MB, 시스템 Python 3.10 이상 필요). 이후 서버는 자동으로 뜸
  - **CLOVA OCR API** — 네이버 클라우드 유료 API, 설정 창에 URL·Secret 입력
- 대사가 바뀌고 타자 효과가 끝난 뒤 한 번만 읽음 (OCR 텍스트가 연속 N 프레임 같을 때). 중간에 읽었으면 이어지는 부분만 읽음
- 화면에 새 이름이 나오면 **화자 자동 등록** → 표에서 더블클릭해 목소리·속도·감정 지정. OCR 오탈자는 자모 단위 유사도 매칭으로 흡수 ("미주"→"민준")
- 미등록 화자·해설(이름 없음) 목소리도 속도·감정까지 지정 (옵션의 [설정] 버튼)
- 재생 정책: **최신 대사만**(새 대사가 오면 끊고 읽기) / **순서대로 모두 읽기**
- 출력 장치 선택 (가상 오디오 장치를 고르면 OBS 등으로 보낼 수 있음)
- TTS 엔진 4종: Edge(무료, 기본) · Typecast(감정) · Google Neural2 · 커스텀(GPT-SoVITS, 내 목소리/캐릭터 목소리 복제)

## 설치

### 설치 마법사 (권장)

[Releases](https://github.com/GankWaL/auto_dubbing_tts/releases) 에서 `AutoDubbingTTS-Setup-<버전>.exe` 를 받아 실행합니다. Python 이 필요 없고, 관리자 권한 없이 현재 사용자에게 설치됩니다 (`%LOCALAPPDATA%\Programs\AutoDubbingTTS`). 설치가 끝나면 바탕화면·시작 메뉴의 **자동 더빙 TTS** 로 바로 실행됩니다.

- 제거: 설정 → 앱 → 설치된 앱 → 자동 더빙 TTS. 설정·EasyOCR 환경·목소리 모델까지 지울지 제거할 때 묻습니다.
- EasyOCR·커스텀 TTS 처럼 무거운 엔진은 설치 파일에 들어 있지 않습니다. EasyOCR 은 컨트롤 패널에서 엔진을 고르면 바로 설치를 제안하고(또는 설치 폴더의 `bat\setup_easyocr.bat`), 커스텀 TTS 는 `bat\setup_tts_server.bat` 으로 따로 만듭니다. 이때만 시스템에 Python 3.10 이상이 필요합니다 (`winget install Python.Python.3.11`).

### 소스로 실행 (개발용)

Python 3.11 이상이 필요합니다.

```bat
bat\setup.bat     :: 최초 1회 — .venv 생성, 라이브러리 설치, .env 생성
bat\start.bat     :: 컨트롤 패널 실행
```

## 사용법

1. 더빙할 프로그램을 띄운 뒤 컨트롤 패널에서 **대사 영역 [선택]** → 화면이 어두워지면 대사 박스를 드래그
2. 이름 박스가 있으면 **이름 영역 [선택]** 도 같은 방법으로
3. **[OCR 테스트]** 로 지금 화면이 제대로 읽히는지 확인 (작은 글자는 "OCR 확대 배율"을 올림, 엔진을 바꿔 비교)
4. **[시작]** — 새 대사가 뜰 때마다 읽어 줍니다. 처음 보는 화자는 표에 자동 추가되니 목소리를 골라 주세요

### 설정 (.env)

컨트롤 패널의 **[설정 (.env)]** 버튼에서 입력합니다 (직접 편집도 가능). 모두 선택 항목입니다.

| 변수 | 설명 |
|---|---|
| `TYPECAST_API_KEY` | Typecast 목소리·감정 활성화 (유료 크레딧) |
| `GOOGLE_TTS_API_KEY` | Google Neural2 목소리 활성화 (월 무료 한도 95% 까지만 사용) |
| `MY_VOICE_ROOT` | 커스텀 목소리(`my_voice`, `my_voice_models`) 폴더. 디스코드 봇 저장소를 지정하면 거기서 학습한 목소리를 그대로 사용 |
| `CLOVA_OCR_URL` / `CLOVA_OCR_SECRET` | 네이버 클라우드 CLOVA OCR API (General) Invoke URL 과 Secret Key |
| `CUSTOM_TTS_URL` / `CUSTOM_TTS_PORT` | 커스텀 TTS 서버 주소·포트 (기본 `127.0.0.1:51770`) |
| `EASYOCR_PORT` | EasyOCR 서버 포트 (기본 `51771`) |

### OCR 엔진 고르기

같은 화면을 두 엔진으로 읽어 본 결과입니다 (맑은 고딕 렌더링, RTX 3070 Ti):

| 항목 | Windows 내장 OCR | CLOVA CRAFT + EasyOCR |
|---|---|---|
| 본문 대사 30px | 정확, 29ms | 마침표→콜론, 일부 오탈자, 105ms |
| 굵은 노란 이름 26px | "민준"→"미주" 오인식, 4ms | 정확, 16ms |
| 작은 글자 16px | 숫자 끼어듦 1자, 16ms | 띄어쓰기·1자 오류, 35ms |

기본은 Windows OCR 이고, 이름 오인식은 자모 매칭이 대부분 흡수합니다. 게임 폰트에 따라 결과가 다르니 **[OCR 테스트]** 로 비교해서 고르세요.

### 게임 화면에서 글자가 깨질 때 (전처리·다중 판독)

반투명 대사 상자, 스캔라인 배경, 굵은 장식 폰트의 이름, 문장 끝에서 깜빡이는 진행 아이콘이 있는 실제 게임 스크린샷으로 원인을 확인하고 다음을 넣었습니다. 모두 기본으로 켜져 있습니다.

| 원인 | 증상 | 대응 |
|---|---|---|
| 영역을 글자에 딱 맞게 잘라 여백이 없음 | 첫 글자 오인식 ("씨"→"피") | 배경색 여백 16px 자동 추가 |
| 확대 배율 하나로만 읽음 | 배율에 따라 다른 글자가 틀림 ("나온"→"나은") | **판독 횟수** 만큼 전처리·배율을 바꿔 읽고 다수결 (기본 3회: 여백 원본, 그레이 1배, 그레이 2배) |
| 색 글씨·장식 폰트 이름 | 이름이 "9월", "기라" 로 깨짐 | 다수결 + 자모 매칭, 이름처럼 보이지 않는 값은 등록하지 않고 직전 화자 유지 |
| 문장 끝 진행 아이콘이 글자로 읽힘 | 같은 대사를 계속 새로 읽음 | 끝의 짧은 기호 토큰 제거 + 글자만 비교해 같은 문장이면 다시 읽지 않음 |
| 이탤릭·기울어진 글씨 | 글자가 완전히 깨짐 (0.70) | **기울기 보정**: 이탤릭 전단을 투영으로 추정해 세움 (0.99). 회전은 Windows OCR 이 스스로 보정 |

판독 횟수를 1 로 두면 한 번만 읽어 가장 빠르고, 4 로 두면 가장 안정적입니다. 대사 한 줄 기준 3회 판독은 150\~250ms 입니다.

### 커스텀 목소리 (GPT-SoVITS)

`bat\setup_tts_server.bat` 으로 추론 환경을 만들고 `bat\start_tts_server.bat` 으로 서버를 띄우면 `my_voice_models\<이름>\` 의 학습 모델 또는 `my_voice\<이름>\` 의 참조 음성(제로샷)이 목소리 목록에 나타납니다. 녹음·학습 방법은 discord_bot_chzzk_tts README 의 "내 목소리" 절과 같습니다. 문장당 2\~7초(RTX 3070 Ti 기준)가 걸리므로 재생 정책을 "최신 대사만"으로 두는 것을 권장합니다.

## 게임 없이 테스트

```bat
bat\fake_vn.bat                                   :: 가짜 비주얼노벨 창 (영역 JSON 출력)
.venv\Scripts\python tests\run_headless.py "<JSON>" --seconds 20
```

또는 fake_vn 창을 띄운 채 컨트롤 패널에서 영역을 드래그해 그대로 사용해도 됩니다.

## 설정 파일

`config\settings.json` 에 영역 좌표, 옵션, 화자 매핑이 저장됩니다.

```json
{
  "regions": {"dialogue": [150, 205, 840, 150], "name": [150, 145, 260, 44]},
  "ocr": {"engine": "windows", "lang": "ko", "scale": 2.0},
  "capture": {"interval_ms": 150, "stable_frames": 3, "change_threshold": 24.0},
  "playback": {"device": null, "policy": "latest", "volume": 1.0},
  "default_speaker": {"voice": "선히", "speed": 1.0, "emotion": "기본"},
  "narrator": {"voice": "인준", "speed": 1.0, "emotion": "기본"},
  "speakers": {"유이": {"voice": "선히", "speed": 1.0, "emotion": "기본"}}
}
```

- `stable_frames`: OCR 텍스트가 이만큼 연속으로 같아야 읽기 시작 (타자 효과 종료 판정). 움직이는 배경 등으로 안정되지 않으면 2초 후 강제로 읽습니다.
- `change_threshold`: 프레임 간 어느 셀이든 밝기 차이(0\~255)가 이보다 크면 화면이 바뀐 것으로 보고 OCR 을 돌립니다. 깜빡이는 화살표는 OCR 텍스트가 같으므로 무시됩니다.

## 구조

```
src\
  main.py            진입점 (DPI 인식 설정 후 GUI)
  gui.py             컨트롤 패널 (영역·시작/정지·화자 표·옵션·설정(.env)·로그)
  dubbing.py         파이프라인: watcher(캡처→변화 감지→OCR) / synth / player 스레드
  capture.py         mss 화면 캡처, 변화 감지 지문
  ocr.py             OCR 공통 인터페이스 + Windows 내장 OCR, create_engine()
  ocr_easyocr.py     CLOVA CRAFT + EasyOCR (같은 프로세스 또는 ocr_server 클라이언트)
  ocr_server.py      EasyOCR 서버 (ocr_env 에서 실행, 앱이 자동으로 띄움)
  ocr_clova.py       CLOVA OCR API 클라이언트
  speakers.py        이름 정리·자모 유사도 매칭·자동 등록, 화자→목소리
  player.py          PC 스피커 재생 큐 (최신만 / 순서대로)
  region_select.py   드래그 영역 선택 오버레이
  config.py          config\settings.json
  tts.py, custom_tts_server.py, setup_custom_tts.py   discord_bot_chzzk_tts 에서 가져온 TTS 엔진
installer\           build.ps1, auto_dubbing.spec (PyInstaller), auto_dubbing.iss (Inno Setup)
tests\               fake_vn.py (가짜 비주얼노벨 창), run_headless.py
bat\                 setup / start / setup_easyocr / start_ocr_server / setup_tts_server / start_tts_server / fake_vn
```

## 빌드 (설치 파일)

```powershell
powershell -ExecutionPolicy Bypass -File installer\build.ps1
```

- 필요: [uv](https://docs.astral.sh/uv/), Inno Setup 6 (`winget install JRSoftware.InnoSetup`)
- `build\venv` 에 빌드 전용 환경(uv 관리 Python 3.11, torch 없음)을 만들고 → PyInstaller 로 `auto_dubbing_tts.exe` 폴더(`build\pyinstaller\AutoDubbingTTS`) → Inno Setup 으로 `build\release\AutoDubbingTTS-Setup-<버전>.exe` 를 만듭니다.
- 버전은 `src\app_version.py` 의 `VERSION` 하나로 관리합니다.
- **릴리스 배포**: `VERSION` 을 올려 커밋·푸시한 뒤 `release-<버전>` 태그를 푸시하면 GitHub Actions 가 설치 파일을 빌드해 릴리스(`v<버전>`)에 올립니다.

```bash
git tag -a release-0.1.0 -m "v0.1.0"
git push origin release-0.1.0
```

## 알려진 제약

- 대사가 세로로 스크롤되는 로그형 UI, 말풍선 위치가 바뀌는 콘텐츠는 지원하지 않습니다.
- OCR 은 장식 폰트·작은 글자에서 오탈자가 납니다. 배율을 올리거나 게임 폰트 크기를 키우고, 엔진을 바꿔 비교해 보세요.
- 커스텀 TTS(GPT-SoVITS)는 문장당 2\~7초가 걸려 빠른 대사 전환을 따라가지 못합니다. 재생 정책 "최신 대사만"을 권장합니다.
- 커스텀 TTS 서버는 디스코드 봇의 서버와 같은 포트(51770)를 씁니다. 둘을 동시에 띄우려면 `.env` 에서 포트를 바꾸세요.
