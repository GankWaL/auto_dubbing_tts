"""화자 이름 정리·매칭과 화자별 목소리 배정."""

import difflib
import re

# 이름 박스에 흔히 붙는 장식 문자: 【유이】, [유이], 유이:, 「유이」 등
_DECOR = re.compile(r"[\[\]【】「」『』()（）<>《》:：\"'“”‘’\s]+")
# 대사 텍스트 정리: OCR 이 남기는 잡문자·중복 공백
_NOISE = re.compile(r"[|_`^~*#=\\]+")
_SPACES = re.compile(r"\s+")

NARRATOR = ""  # 이름이 없는 대사(해설)의 화자 키


def clean_name(text: str) -> str:
    return _DECOR.sub("", text).strip()


def clean_dialogue(text: str) -> str:
    text = _NOISE.sub("", text)
    text = text.replace("\n", " ")
    return _SPACES.sub(" ", text).strip()


_CHO = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
_JUNG = "ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ"
_JONG = " ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ"


def to_jamo(text: str) -> str:
    """한글 음절을 초·중·종성으로 풀어 쓴다. '민준'→'ㅁㅣㄴㅈㅜㄴ'.

    OCR 오탈자는 음절 단위로는 전혀 다른 글자(민→미)라도 자모 단위로는 대부분 겹치므로
    이 표현으로 비교하면 짧은 이름도 잘 맞는다.
    """
    out = []
    for ch in text:
        code = ord(ch) - 0xAC00
        if 0 <= code < 11172:
            cho, rest = divmod(code, 588)
            jung, jong = divmod(rest, 28)
            out.append(_CHO[cho] + _JUNG[jung] + (_JONG[jong] if jong else ""))
        else:
            out.append(ch)
    return "".join(out)


def closest_name(name: str, candidates: list[str], cutoff: float) -> str | None:
    """자모 단위 유사도가 cutoff 이상인 가장 비슷한 이름. 없으면 None."""
    target = to_jamo(name)
    best, best_ratio = None, 0.0
    for cand in candidates:
        ratio = difflib.SequenceMatcher(None, target, to_jamo(cand)).ratio()
        if ratio > best_ratio:
            best, best_ratio = cand, ratio
    return best if best_ratio >= cutoff else None


class SpeakerBook:
    """settings["speakers"] 를 감싸 이름 매칭과 자동 등록을 담당한다."""

    def __init__(self, settings: dict):
        self.settings = settings

    @property
    def speakers(self) -> dict:
        return self.settings["speakers"]

    def resolve(self, raw_name: str, cutoff: float = 0.75) -> tuple[str, bool]:
        """OCR 이름 → (등록 이름, 새로 등록됐는지).

        OCR 오탈자를 흡수하기 위해 등록된 이름과 유사도 매칭을 먼저 시도하고,
        없으면 기본 목소리로 자동 등록한다. 빈 이름은 해설(NARRATOR)로 본다.
        """
        name = clean_name(raw_name)
        if not name:
            return NARRATOR, False
        if name in self.speakers:
            return name, False
        match = closest_name(name, list(self.speakers), cutoff)
        if match:
            return match, False
        self.speakers[name] = {
            "voice": self.settings["default_voice"],
            "speed": 1.0,
            "emotion": "기본",
        }
        return name, True

    def voice_for(self, name: str) -> dict:
        if name == NARRATOR:
            return {"voice": self.settings["narrator_voice"], "speed": 1.0, "emotion": "기본"}
        cfg = self.speakers.get(name, {})
        return {
            "voice": cfg.get("voice", self.settings["default_voice"]),
            "speed": float(cfg.get("speed", 1.0)),
            "emotion": cfg.get("emotion", "기본"),
        }
