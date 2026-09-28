# auto_dubbing_tts 작업 규칙

화면의 대사 박스를 OCR 로 읽어 화자별 목소리로 자동 더빙하는 Windows 프로그램.
공통 규칙은 `~/claude-harness/CLAUDE.md` 를 따른다. 여기는 이 프로젝트 한정 규칙만 적는다.

## 개요·범위

- 대상은 이름 박스 + 대사 박스가 고정 위치인 콘텐츠(비주얼노벨·게임)다. 영상 자막, 웹툰은 범위 밖.
- OCR 엔진은 3종이다: Windows 내장(기본, `winrt-Windows.Media.Ocr`), CLOVA CRAFT + EasyOCR(`src/ocr_easyocr.py`, 별도 환경 ocr_env 의 `ocr_server.py` 로 실행), CLOVA OCR API(`src/ocr_clova.py`). 새 엔진은 `ocr.BaseOcr` 를 구현해 `ocr.ENGINES`·`create_engine()` 에 등록한다. torch 같은 무거운 의존성은 exe 에 넣지 않고 서버 방식으로 분리한다.
- 벤치마크(2026-09-29, 맑은 고딕 렌더링): 본문은 Windows OCR 이 정확하고 빠르며(29ms), 굵은 이름 박스는 EasyOCR 이 정확하다("민준" 대 Windows "미주"). 이름 오인식은 `speakers.closest_name` 의 자모 매칭이 흡수한다.
- 실제 게임 스크린샷(반투명 상자·보라 굵은 이름 '키라'·끝 아이콘) 조사 결과와 대응은 README "게임 화면에서 글자가 깨질 때" 표에 있다. 핵심 규칙:
  - OCR 은 항상 `recognize_robust()`(다중 판독 다수결 + 기울기 보정)로 호출한다. `recognize()` 직접 호출은 엔진 내부용.
  - 판독 조합 `ocr.pass_plan` 은 스크린샷 4조건(대사 타이트/느슨, 이름 타이트/느슨)으로 탐색한 결과다. 바꾸려면 같은 방식으로 재측정한다 (임시 스크립트, 저장소에 두지 않음).
  - Windows OCR 은 회전을 스스로 보정하고 단어 상자를 보정 좌표로 주므로 `angle_from_words` 는 EasyOCR·CLOVA API 에서만 의미가 있다. 이탤릭(전단)은 `estimate_shear` 로 보정한다 (0.70→0.99).
  - 문장 동일성은 `speakers.same_sentence`(글자만 비교, 꼬리 2자·유사도 0.92)로 판단한다. 대사 끝 아이콘 깜빡임 재읽기 버그의 재발 방지 장치이니 완화하지 않는다.
  - 이름처럼 보이지 않는 OCR 값(`looks_like_name` 거짓)은 화자로 등록하지 않고 직전 화자를 유지한다.
- 재생은 **이 프로그램이 직접 PC 스피커로 출력**한다(`src/player.py`, sounddevice). 디스코드 연동은 넣지 않는다.
- TTS 엔진 모듈 `src/tts.py` 와 커스텀 서버 `src/custom_tts_server.py` 는 `discord_bot_chzzk_tts` 저장소에서 가져온 복사본이다. 엔진 관련 수정은 원본 저장소와 같이 맞춘다. `available_voices()`·`synthesize()` 인터페이스는 바꾸지 않는다.

## 구조

```text
src/
  main.py          진입점 (DPI 인식 설정 후 GUI)
  gui.py           tkinter 컨트롤 패널: 영역 선택·시작/정지·화자 표·옵션·로그
  dubbing.py       파이프라인: watcher(캡처→변화 감지→OCR) / synth / player 스레드
  capture.py       mss 화면 캡처, 변화 감지 지문
  ocr.py           OCR 공통 인터페이스(BaseOcr, ENGINES, create_engine) + Windows 내장 OCR
  ocr_easyocr.py   CLOVA CRAFT + EasyOCR — 같은 프로세스(Local) 또는 ocr_server 클라이언트(Remote, 자동 기동)
  ocr_server.py    EasyOCR HTTP 서버 (ocr_env 에서 실행, 포트 51771)
  ocr_setup.py     ocr_env 설치 (시스템 Python 탐색, GPU 유무로 CUDA/CPU torch) — GUI "지금 설치" 와 bat 이 공용
  ocr_clova.py     네이버 클라우드 CLOVA OCR API 클라이언트
  speakers.py      이름 정리·자모 유사도 매칭·자동 등록, 화자→목소리
  player.py        재생 큐 (policy: latest | queue)
  region_select.py 드래그 영역 선택 오버레이
  config.py        config/settings.json 로드·저장
  app_version.py   VERSION (설치 파일·릴리스 태그 기준)
  tts.py, custom_tts_server.py, setup_custom_tts.py   (discord_bot_chzzk_tts 복사본)
installer/         build.ps1, auto_dubbing.spec (PyInstaller), auto_dubbing.iss (Inno Setup)
tests/
  fake_vn.py       가짜 비주얼노벨 창 (타자 효과·깜빡이는 화살표 포함)
  run_headless.py  GUI 없이 파이프라인 실행
```

## 실행·검증

- 실행: `bat\start.bat` (최초 `bat\setup.bat`). 개발 중에는 `.venv\Scripts\python src\main.py`.
- 게임 없이 검증: 터미널 1 에서 `.venv\Scripts\python tests\fake_vn.py` 를 띄우면 영역 JSON 이 출력되고, 터미널 2 에서 `.venv\Scripts\python tests\run_headless.py '<그 JSON>' --seconds 20` 로 로그를 본다. 코드 수정 후에는 이 흐름으로 한 번 돌려 확인한다.
- OCR 단독 확인: `.venv\Scripts\python src\ocr.py <이미지>`.
- 콘솔에서 한글이 깨지면 `PYTHONIOENCODING=utf-8` 로 실행한다.

## 빌드·릴리스

- 설치 파일: `powershell -ExecutionPolicy Bypass -File installer\build.ps1` → `build\release\AutoDubbingTTS-Setup-<버전>.exe`. 빌드 환경은 `build\venv`(uv 관리 Python, torch 없음)이고 개발용 `.venv`(torch·easyocr 포함)와 분리한다. spec 의 `excludes` 에 torch·easyocr 이 있다.
- 버전은 `src/app_version.py` 의 `VERSION` 하나. 릴리스는 `release-<버전>` 태그 푸시 → `.github/workflows/release.yml`.
- 빌드 후 확인: `build\pyinstaller\AutoDubbingTTS\auto_dubbing_tts.exe` 를 실행해 창 제목 `자동 더빙 TTS v<버전>` 이 뜨는지 본다. exe 는 winrt 를 `collect_all("winrt")` 로 넣어야 OCR 이 동작한다.
- 설치본에서 별도 환경으로 실행되는 소스(`ocr.py`, `ocr_easyocr.py`, `ocr_server.py`, `ocr_setup.py`, `custom_tts_server.py`, `setup_custom_tts.py`)와 bat 은 `installer/auto_dubbing.iss` 의 [Files] 에 명시돼 있다. 새 서버 모듈을 만들면 여기에도 추가한다.

## 주의

- mss 인스턴스와 OCR 엔진은 스레드에 묶이므로 사용하는 스레드 안에서 만든다 (watcher 스레드).
- 파이프라인 검증 후 `config/settings.json` 에 테스트 화자가 남지 않았는지 본다 (`tests/run_headless.py` 는 저장을 막아 둔다).
- tkinter 좌표와 캡처 픽셀이 어긋나지 않도록 `main.py` 에서 DPI 인식을 켠다. 새 진입점을 만들면 같은 처리를 넣는다.
- `config/settings.json` 은 사용자 설정(영역·화자 매핑)이므로 커밋하지 않는다.
- 커스텀 목소리 폴더·서버 포트는 `.env` 의 `MY_VOICE_ROOT`, `CUSTOM_TTS_URL`, `CUSTOM_TTS_PORT` 로 바꾼다. 디스코드 봇의 서버(51770)와 동시에 띄우면 포트가 겹치니 한쪽만 띄우거나 포트를 바꾼다.
