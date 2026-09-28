"""화자 이름 정리·매칭과 화자별 목소리 배정."""

import difflib
import re

# 이름 박스에 흔히 붙는 장식 문자: 【유이】, [유이], 유이:, 「유이」 등
_DECOR = re.compile(r"[\[\]【】「」『』()（）<>《》:：\"'“”‘’\s]+")
# 대사 텍스트 정리: OCR 이 남기는 잡문자·중복 공백
_NOISE = re.compile(r"[|_`^*#=\\]+")  # '~' 는 "와~" 처럼 대사에 쓰이므로 남긴다
_SPACES = re.compile(r"\s+")

NARRATOR = ""  # 이름이 없는 대사(해설)의 화자 키


_NAME_EDGE = re.compile(r"^[^가-힣ㄱ-ㅎㅏ-ㅣA-Za-z]+|[^가-힣ㄱ-ㅎㅏ-ㅣA-Za-z]+$")


def clean_name(text: str) -> str:
    """장식 문자를 떼고, 이름 앞뒤에 붙은 글자 아닌 것('키라7' 의 7 — 상자 테두리 오인식)을 자른다."""
    return _NAME_EDGE.sub("", _DECOR.sub("", text).strip())


_HAS_LETTER = re.compile(r"[가-힣ㄱ-ㅎㅏ-ㅣA-Za-z]")
# 앞뒤에 붙는 짧은 쓰레기 토큰: 대사 끝의 진행 화살표·아이콘이 ':' '(71' '『' 처럼 읽힌 것
_MAX_JUNK_TOKEN = 3


def _is_junk_token(tok: str, keep_sentence_end: bool) -> bool:
    if len(tok) > _MAX_JUNK_TOKEN or _HAS_LETTER.search(tok):
        return False
    return not (keep_sentence_end and tok[-1] in ".!?…")


def _strip_junk_tokens(tokens: list[str]) -> list[str]:
    while tokens and _is_junk_token(tokens[-1], keep_sentence_end=True):
        tokens.pop()
    while tokens and _is_junk_token(tokens[0], keep_sentence_end=False):
        tokens.pop(0)
    return tokens


def clean_dialogue(text: str) -> str:
    text = _NOISE.sub("", text)
    text = text.replace("\n", " ")
    text = _SPACES.sub(" ", text).strip()
    if not text:
        return ""
    return " ".join(_strip_junk_tokens(text.split(" ")))


_CORE = re.compile(r"[^가-힣ㄱ-ㅎㅏ-ㅣA-Za-z0-9]")


def core_text(text: str) -> str:
    """비교용 — 글자·숫자만 남긴다 (공백·문장부호·기호 제거)."""
    return _CORE.sub("", text)


def same_sentence(a: str, b: str, min_ratio: float = 0.92, tail: int = 2) -> bool:
    """두 OCR 결과가 같은 문장인가.

    문장 끝의 진행 아이콘·그림이 깜빡이며 글자로 잘못 읽히면 텍스트가 매 프레임 조금씩 달라져
    같은 대사를 계속 새로 읽게 된다. 글자만 남긴 뒤 (1) 같거나 (2) 한쪽이 다른 쪽 + 짧은 꼬리이거나
    (3) 유사도가 min_ratio 이상이면 같은 문장으로 본다 (한 글자 흔들림 '나온/나은' 도 흡수).
    """
    ca, cb = core_text(a), core_text(b)
    if ca == cb:
        return True
    if not ca or not cb:
        return False
    short, long = sorted((ca, cb), key=len)
    if long.startswith(short) and len(long) - len(short) <= tail:
        return True
    return difflib.SequenceMatcher(None, ca, cb).ratio() >= min_ratio


def looks_like_name(name: str, max_len: int = 12) -> bool:
    """화자 이름으로 볼 만한가 — 글자가 하나라도 있고 너무 길지 않고 절반 이상이 글자."""
    if not name or len(name) > max_len:
        return False
    letters = len(_HAS_LETTER.findall(name))
    return letters >= 1 and letters * 2 >= len(name)


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

    def resolve(self, raw_name: str, cutoff: float = 0.75,
                previous: str | None = None) -> tuple[str, bool]:
        """OCR 이름 → (등록 이름, 새로 등록됐는지).

        OCR 오탈자를 흡수하기 위해 등록된 이름과 자모 유사도 매칭을 먼저 시도하고,
        없으면 기본 목소리로 자동 등록한다. 빈 이름은 해설(NARRATOR)로 본다.
        이름처럼 보이지 않는 값(기호·숫자 위주, 장식 폰트가 깨진 것)은 등록하지 않고
        직전 화자(previous)를 유지한다 — 화자 표가 쓰레기 이름으로 채워지는 것을 막는다.
        """
        name = clean_name(raw_name)
        if not name:
            return NARRATOR, False
        if name in self.speakers:
            return name, False
        match = closest_name(name, list(self.speakers), cutoff)
        if match:
            return match, False
        if not looks_like_name(name):
            return (previous if previous is not None else NARRATOR), False
        self.speakers[name] = dict(self.settings["default_speaker"])
        return name, True

    def voice_for(self, name: str) -> dict:
        if name == NARRATOR:
            cfg = self.settings["narrator"]
        else:
            cfg = self.speakers.get(name) or self.settings["default_speaker"]
        return {
            "voice": cfg.get("voice", self.settings["default_speaker"]["voice"]),
            "speed": float(cfg.get("speed", 1.0)),
            "emotion": cfg.get("emotion", "기본"),
        }
