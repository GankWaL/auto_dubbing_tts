"""TTS 엔진 모듈 (discord_bot_chzzk_tts 의 tts.py 를 가져와 경로만 조정).

- Edge TTS: 무료, 기본 엔진.
- Typecast: .env 에 TYPECAST_API_KEY 가 있으면 목소리 목록에 추가된다. (유료 크레딧 소모)
- Google Cloud TTS (Neural2): .env 에 GOOGLE_TTS_API_KEY 가 있으면 추가된다.
  월 무료 한도(100만 자)의 95%까지만 사용하고, 초과 시 Edge TTS로 자동 전환된다.

교체/추가 시 available_voices() 와 synthesize() 인터페이스만 유지하면 된다.
"""

import base64
import json
from datetime import datetime
import os
import sys
import tempfile

import aiohttp
import edge_tts
from dotenv import load_dotenv

# 프로젝트 루트: exe(PyInstaller)면 실행 파일 위치, 아니면 src/ 의 상위 폴더
BASE_DIR = (
    os.path.dirname(sys.executable)
    if getattr(sys, "frozen", False)
    else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

load_dotenv(os.path.join(BASE_DIR, ".env"))

TYPECAST_URL = "https://api.typecast.ai/v1/text-to-speech"
TYPECAST_SUBSCRIPTION_URL = "https://api.typecast.ai/v1/users/me/subscription"
TYPECAST_MODEL = "ssfm-v30"

# 커스텀 TTS(내 목소리) 추론 서버 — bat\start_tts_server.bat 로 실행.
# .env 의 CUSTOM_TTS_URL 로 바꿀 수 있다 (예: 디스코드 봇이 띄운 서버를 같이 쓸 때).
CUSTOM_TTS_URL = os.getenv("CUSTOM_TTS_URL", "http://127.0.0.1:51770")
# 커스텀 목소리(my_voice, my_voice_models) 위치 — .env 의 MY_VOICE_ROOT 로 바꿀 수 있다.
# 디스코드 봇에서 학습한 목소리를 그대로 쓰려면 그 저장소 경로를 지정한다.
_ROOT_DIR = os.getenv("MY_VOICE_ROOT", BASE_DIR)
MY_VOICE_DIR = os.path.join(_ROOT_DIR, "my_voice")

GOOGLE_TTS_URL = "https://texttospeech.googleapis.com/v1/text:synthesize"
# Neural2 월 무료 한도(100만 자) — 과금 방지를 위해 95%에서 차단
GOOGLE_FREE_LIMIT = 1_000_000
GOOGLE_SAFE_LIMIT = int(GOOGLE_FREE_LIMIT * 0.95)
GOOGLE_USAGE_FILE = os.path.join(BASE_DIR, "google_tts_usage.json")

# 표시 이름 -> {engine, id}
EDGE_VOICES = {
    "선히": {"engine": "edge", "id": "ko-KR-SunHiNeural"},
    "인준": {"engine": "edge", "id": "ko-KR-InJoonNeural"},
    "현수": {"engine": "edge", "id": "ko-KR-HyunsuMultilingualNeural"},
}

# Typecast 한국어 음성 중 일부만 선별 (전체 목록: https://studio.typecast.ai/developers/api/voices)
TYPECAST_VOICES = {
    #남자
    "스모크": {"engine": "typecast", "id": "tc_60126fbf8e097503c73ed8d6"},
    "팡팡": {"engine": "typecast", "id": "tc_61532cab9119555d352f5c69"},
    "아봉": {"engine": "typecast", "id": "tc_61532c5aed9bfa8b54d5dff6"},
    "덕구": {"engine": "typecast", "id": "tc_618203826672d21ebf37748e"},
    "콩": {"engine": "typecast", "id": "tc_623145ec8d2f689cc9bad6d5"},
    "바바": {"engine": "typecast", "id": "tc_62a89753894c1004cb577d04"},
    "치프": {"engine": "typecast", "id": "tc_62df8e39067dcda7c2b34347"},
    "너굴": {"engine": "typecast", "id": "tc_6359e7ea258d1b6dc3abe6e6"},
    "졸리": {"engine": "typecast", "id": "tc_6386d6aceb3125e51e3234e8"},
    "민수": {"engine": "typecast", "id": "tc_63a3d9da4b235ddd6541a795"},
    "고트": {"engine": "typecast", "id": "tc_6747f7c4b4470b54ab8a06bc"},
    "틸": {"engine": "typecast", "id": "tc_63f7168722ebe13991293cde"},
    "설록": {"engine": "typecast", "id": "tc_63da42a2dbbf266ceb0b0fb2"},
    "반장": {"engine": "typecast", "id": "tc_63aaebf1cef3e7d6ce6d3628"},
    "찬구1": {"engine": "typecast", "id": "tc_5c547544fcfee90007fed455", "desc": "기본"},
    "찬구2": {"engine": "typecast", "id": "tc_6010088f885570093ad24d53", "desc": "삐뚤어진 톤"},
    #여자
    "루리": {"engine": "typecast", "id": "tc_65a8c82a7e7bded32947497e"},
    "보노": {"engine": "typecast", "id": "tc_5c547544fcfee90007fed454"},
    "아찌": {"engine": "typecast", "id": "tc_66596206b7bd6e89c3a2c54e"},
    "소율": {"engine": "typecast", "id": "tc_62b17f026fe31dc29ac8e94e"},
    "숙희": {"engine": "typecast", "id": "tc_61c2f70c343884babeed840b"},
    "데이지": {"engine": "typecast", "id": "tc_60bf72699042ef1da40214c7"},
    "순이": {"engine": "typecast", "id": "tc_60ad0841061ee28740ec2e1c"},
    "발키리": {"engine": "typecast", "id": "tc_60478557f12456064b353409"},
    "아리": {"engine": "typecast", "id": "tc_6047863af12456064b35354e"},
    "채린이": {"engine": "typecast", "id": "tc_5ffda44bcba8f6d3d46fc41f"},
}

DEFAULT_VOICE = "선히"

# Typecast 감정 프리셋 (한글 이름 -> API 값). Typecast 목소리에만 적용된다.
TYPECAST_EMOTIONS = {
    "기본": "normal",
    "기쁨": "happy",
    "슬픔": "sad",
    "화남": "angry",
    "속삭임": "whisper",
    "톤업": "toneup",
    "톤다운": "tonedown",
}
DEFAULT_EMOTION = "기본"

# 재생 속도(배속) 범위 — Typecast audio_tempo 지원 범위에 맞춤
MIN_SPEED = 0.5
MAX_SPEED = 2.0
DEFAULT_SPEED = 1.0


# Google Cloud TTS 한국어 Neural2 음성
GOOGLE_VOICES = {
    "구글1": {"engine": "google", "id": "ko-KR-Neural2-A", "desc": "여성"},
    "구글2": {"engine": "google", "id": "ko-KR-Neural2-B", "desc": "여성"},
    "구글3": {"engine": "google", "id": "ko-KR-Neural2-C", "desc": "남성"},
}


def _typecast_key() -> str | None:
    return os.getenv("TYPECAST_API_KEY")


def _google_key() -> str | None:
    return os.getenv("GOOGLE_TTS_API_KEY")


MY_VOICE_MODELS_DIR = os.path.join(_ROOT_DIR, "my_voice_models")


def custom_voices() -> dict[str, dict]:
    """커스텀(내 목소리) 목록 — 녹음 데이터(제로샷) + 학습된 모델(파인튜닝)."""
    voices = {}
    if os.path.isdir(MY_VOICE_DIR):
        for name in sorted(os.listdir(MY_VOICE_DIR)):
            meta = os.path.join(MY_VOICE_DIR, name, "metadata.csv")
            if os.path.isfile(meta) and os.path.getsize(meta) > 0:
                voices[name] = {"engine": "custom", "id": name, "desc": "내 목소리"}
    if os.path.isdir(MY_VOICE_MODELS_DIR):
        for name in sorted(os.listdir(MY_VOICE_MODELS_DIR)):
            model_dir = os.path.join(MY_VOICE_MODELS_DIR, name)
            if os.path.isfile(os.path.join(model_dir, "sovits.pth")) and os.path.isfile(
                os.path.join(model_dir, "gpt.ckpt")
            ):
                voices[name] = {"engine": "custom", "id": name, "desc": "내 목소리 (학습됨)"}
    return voices


def available_voices() -> dict[str, dict]:
    """현재 사용 가능한 음성 목록. Typecast/Google은 API 키가 있을 때만 포함된다."""
    voices = dict(EDGE_VOICES)
    if _typecast_key():
        voices.update(TYPECAST_VOICES)
    if _google_key():
        voices.update(GOOGLE_VOICES)
    voices.update(custom_voices())
    return voices


def google_usage() -> dict:
    """이번 달 Google TTS 사용량({month, chars}). 달이 바뀌면 자동 리셋된다."""
    month = datetime.now().strftime("%Y-%m")
    try:
        with open(GOOGLE_USAGE_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = {}
    if data.get("month") != month:
        data = {"month": month, "chars": 0}
    return data


def _add_google_usage(chars: int) -> None:
    data = google_usage()
    data["chars"] += chars
    with open(GOOGLE_USAGE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f)


def google_quota_left() -> int:
    """무료 한도 안전선(95%)까지 남은 글자 수."""
    return max(0, GOOGLE_SAFE_LIMIT - google_usage()["chars"])


async def typecast_credits() -> dict | None:
    """Typecast 플랜/크레딧 정보를 반환한다. API 키가 없으면 None."""
    key = _typecast_key()
    if not key:
        return None
    async with aiohttp.ClientSession() as session:
        async with session.get(
            TYPECAST_SUBSCRIPTION_URL,
            headers={"X-API-KEY": key},
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            resp.raise_for_status()
            return await resp.json()


async def synthesize(
    text: str,
    voice_name: str,
    speed: float = DEFAULT_SPEED,
    emotion: str = DEFAULT_EMOTION,
) -> str:
    """텍스트를 음성으로 합성하고 생성된 오디오 파일 경로를 반환한다.

    speed 는 0.5~2.0 배속. emotion 은 TYPECAST_EMOTIONS 의 한글 이름이며
    Typecast 목소리에만 적용된다. 호출한 쪽에서 재생 후 파일을 삭제해야 한다.
    """
    speed = max(MIN_SPEED, min(MAX_SPEED, speed))
    voice = available_voices().get(voice_name) or EDGE_VOICES[DEFAULT_VOICE]
    if voice["engine"] == "custom":
        return await _synthesize_custom(text, voice["id"], speed)
    if voice["engine"] == "typecast":
        return await _synthesize_typecast(text, voice["id"], speed, emotion)
    if voice["engine"] == "google":
        # 무료 한도 안전선 초과 시 과금 방지를 위해 Edge TTS로 자동 전환
        if len(text) > google_quota_left():
            return await _synthesize_edge(
                text, EDGE_VOICES[DEFAULT_VOICE]["id"], speed
            )
        path = await _synthesize_google(text, voice["id"], speed)
        _add_google_usage(len(text))
        return path
    return await _synthesize_edge(text, voice["id"], speed)


def _make_temp(suffix: str) -> str:
    fd, path = tempfile.mkstemp(suffix=suffix, prefix="auto_dub_")
    os.close(fd)
    return path


def _cleanup(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


async def _synthesize_edge(text: str, voice_id: str, speed: float) -> str:
    rate = f"{round((speed - 1) * 100):+d}%"
    path = _make_temp(".mp3")
    try:
        await edge_tts.Communicate(text, voice_id, rate=rate).save(path)
    except Exception:
        _cleanup(path)
        raise
    return path


async def warmup_custom(voice_name: str) -> None:
    """커스텀 목소리 웜업 요청 — 실패해도 무시 (첫 합성이 조금 느려질 뿐)."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{CUSTOM_TTS_URL}/warmup",
                json={"voice": voice_name},
                timeout=aiohttp.ClientTimeout(total=300),
            ):
                pass
    except Exception:
        pass


async def _synthesize_custom(text: str, voice_name: str, speed: float = DEFAULT_SPEED) -> str:
    """로컬 추론 서버(GPT-SoVITS)로 내 목소리 합성. 감정은 미지원."""
    payload = {"text": text, "voice": voice_name, "speed": speed}
    path = _make_temp(".wav")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{CUSTOM_TTS_URL}/synthesize",
                json=payload,
                # 첫 요청은 모델 로드/교체(1~2분)가 포함될 수 있어 여유 있게
                timeout=aiohttp.ClientTimeout(total=300),
            ) as resp:
                if resp.status != 200:
                    detail = await resp.text()
                    raise RuntimeError(f"커스텀 TTS 서버 오류: {detail[:200]}")
                data = await resp.read()
        with open(path, "wb") as f:
            f.write(data)
    except aiohttp.ClientConnectorError:
        _cleanup(path)
        raise RuntimeError(
            "커스텀 TTS 서버가 실행되어 있지 않습니다. bat\\start_tts_server.bat 을 먼저 실행해주세요."
        )
    except Exception:
        _cleanup(path)
        raise
    return path


async def _synthesize_google(text: str, voice_id: str, speed: float) -> str:
    payload = {
        "input": {"text": text},
        "voice": {"languageCode": "ko-KR", "name": voice_id},
        "audioConfig": {"audioEncoding": "MP3", "speakingRate": speed},
    }
    path = _make_temp(".mp3")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{GOOGLE_TTS_URL}?key={_google_key()}",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                resp.raise_for_status()
                data = await resp.json()
        with open(path, "wb") as f:
            f.write(base64.b64decode(data["audioContent"]))
    except Exception:
        _cleanup(path)
        raise
    return path


async def _synthesize_typecast(
    text: str, voice_id: str, speed: float, emotion: str = DEFAULT_EMOTION
) -> str:
    payload = {
        "text": text,
        "model": TYPECAST_MODEL,
        "voice_id": voice_id,
        "output": {"audio_tempo": speed},
    }
    preset = TYPECAST_EMOTIONS.get(emotion)
    if preset and preset != "normal":
        payload["prompt"] = {"emotion_type": "preset", "emotion_preset": preset}
    headers = {"X-API-KEY": _typecast_key()}
    path = _make_temp(".wav")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                TYPECAST_URL,
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                resp.raise_for_status()
                data = await resp.read()
        with open(path, "wb") as f:
            f.write(data)
    except Exception:
        _cleanup(path)
        raise
    return path
