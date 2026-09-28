"""커스텀 TTS(GPT-SoVITS) 환경 마무리 설정 — tts_env 파이썬으로 실행.

bat\\setup_tts_server.bat 이 호출한다. 하는 일:
1. 사전학습 모델 다운로드 (HuBERT / BERT / v2 파운데이션)
2. .bin 가중치를 safetensors 로 변환 (최신 transformers 의 torch.load 제한 우회)
3. Windows 호환 심 설치 (jieba_fast → jieba, eunjeon → python-mecab-ko)
모두 멱등(재실행 안전)하다.
"""

import os
import site
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.join(BASE_DIR, "GPT-SoVITS")
PRETRAINED = os.path.join(REPO, "GPT_SoVITS", "pretrained_models")


def download_pretrained() -> None:
    from huggingface_hub import snapshot_download

    print("[설정] 사전학습 모델 확인/다운로드 중...")
    snapshot_download(
        "lj1995/GPT-SoVITS",
        local_dir=PRETRAINED,
        allow_patterns=[
            "gsv-v2final-pretrained/*",
            "chinese-hubert-base/*",
            "chinese-roberta-wwm-ext-large/*",
        ],
        # s2D 는 학습(판별자)에만 쓰이고 추론에는 불필요 — 89MB 절약
        ignore_patterns=["gsv-v2final-pretrained/s2D*.pth"],
    )
    print("[설정] 사전학습 모델 준비 완료")


def convert_safetensors() -> None:
    import torch
    from safetensors.torch import save_file

    for sub in ("chinese-roberta-wwm-ext-large", "chinese-hubert-base"):
        d = os.path.join(PRETRAINED, sub)
        dst = os.path.join(d, "model.safetensors")
        src = os.path.join(d, "pytorch_model.bin")
        if os.path.exists(dst) or not os.path.exists(src):
            continue
        print(f"[설정] safetensors 변환 중: {sub}")
        sd = torch.load(src, map_location="cpu", weights_only=True)
        sd = {k: v.clone().contiguous() for k, v in sd.items()}
        save_file(sd, dst, metadata={"format": "pt"})
        os.remove(src)  # 변환 후 원본 .bin 은 불필요 (중복 용량)
    print("[설정] safetensors 변환 완료")


def install_shims() -> None:
    site_dir = site.getsitepackages()[-1] if site.getsitepackages() else None
    for candidate in site.getsitepackages():
        if candidate.endswith("site-packages"):
            site_dir = candidate
            break
    if not site_dir:
        raise SystemExit("site-packages 경로를 찾지 못했습니다")

    jf = os.path.join(site_dir, "jieba_fast")
    os.makedirs(jf, exist_ok=True)
    with open(os.path.join(jf, "__init__.py"), "w", encoding="utf-8") as f:
        f.write("# jieba_fast shim -> pure-python jieba\nfrom jieba import *  # noqa\n"
                "import jieba as _j\nfor _k in dir(_j):\n"
                "    if not _k.startswith('__'):\n        globals().setdefault(_k, getattr(_j, _k))\n")
    with open(os.path.join(jf, "posseg.py"), "w", encoding="utf-8") as f:
        f.write("from jieba.posseg import *  # noqa\nimport jieba.posseg as _p\n"
                "for _k in dir(_p):\n"
                "    if not _k.startswith('__'):\n        globals().setdefault(_k, getattr(_p, _k))\n")

    ej = os.path.join(site_dir, "eunjeon")
    os.makedirs(ej, exist_ok=True)
    with open(os.path.join(ej, "__init__.py"), "w", encoding="utf-8") as f:
        f.write("# eunjeon shim -> python-mecab-ko\nfrom mecab import MeCab as Mecab\n")
    print("[설정] Windows 호환 심 설치 완료 (jieba_fast, eunjeon)")


def main() -> None:
    if sys.stdout:
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass
    if not os.path.isdir(REPO):
        raise SystemExit("GPT-SoVITS 저장소가 없습니다. bat\\setup_tts_server.bat 으로 실행해주세요.")
    download_pretrained()
    convert_safetensors()
    install_shims()
    print("[설정] 모든 설정 완료! bat\\start_tts_server.bat 으로 서버를 실행하세요.")


if __name__ == "__main__":
    main()
