"""Paths and lookups shared by the translate-video scripts. Standard library only, so get_models.py --sizes can run
before the Python environment exists."""
import json
import os
import subprocess
from pathlib import Path

HOME = Path(os.environ.get("TRANSLATE_VIDEO_HOME", str(Path.home() / ".cache" / "translate-video")))
MODELS = HOME / "models"
BIN = HOME / "bin"
WORK_ROOT = HOME / "work"
PYTHON = HOME / "venv" / "bin" / "python"
SCRIPTS = Path(__file__).resolve().parent

FONT_FILE = "/System/Library/Fonts/HelveticaNeue.ttc"
FONT_MEDIUM, FONT_BOLD = 10, 1  # face numbers inside the .ttc

MAIN_MODEL = "whisper-large-v3-mlx"
# A second model with different training catches mishearings where the two transcripts disagree.
SECOND_MODEL = {"ja": "kotoba-v2.0-faster"}  # trained on Japanese TV speech
SECOND_FALLBACK = "faster-whisper-large-v3"  # optional for other languages: same Whisper, different decoder
MODEL_FILES = {
    "whisper-large-v3-mlx": ("mlx-community/whisper-large-v3-mlx", ["config.json", "weights.npz"]),
    "kotoba-v2.0-faster": (
        "kotoba-tech/kotoba-whisper-v2.0-faster",
        ["config.json", "model.bin", "preprocessor_config.json", "tokenizer.json", "vocabulary.json"],
    ),
    "faster-whisper-large-v3": (
        "Systran/faster-whisper-large-v3",
        ["config.json", "model.bin", "preprocessor_config.json", "tokenizer.json", "vocabulary.json"],
    ),
}
CHUNK_LENGTH = {"kotoba-v2.0-faster": 15}  # seconds per window; Kotoba's authors recommend 15

# Apple Vision text-recognition languages, by Whisper language code.
OCR_LANGS = {
    "ja": ["ja-JP", "en-US"], "zh": ["zh-Hans", "zh-Hant", "en-US"], "yue": ["yue-Hant", "zh-Hant", "en-US"],
    "ko": ["ko-KR", "en-US"], "fr": ["fr-FR", "en-US"], "de": ["de-DE", "en-US"], "es": ["es-ES", "en-US"],
    "it": ["it-IT", "en-US"], "pt": ["pt-BR", "en-US"], "ru": ["ru-RU", "en-US"], "uk": ["uk-UA", "en-US"],
    "th": ["th-TH", "en-US"], "vi": ["vi-VT", "en-US"], "ar": ["ar-SA", "en-US"],
}
# ISO 639-2 audio language tags, by Whisper language code, and the older spellings that mean the same.
LANG3 = {
    "ja": "jpn", "zh": "zho", "yue": "yue", "ko": "kor", "fr": "fra", "de": "deu", "es": "spa", "it": "ita",
    "pt": "por", "ru": "rus", "uk": "ukr", "th": "tha", "vi": "vie", "ar": "ara", "en": "eng", "he": "heb",
    "hi": "hin", "id": "ind", "tr": "tur", "nl": "nld", "pl": "pol",
}
LANG3_ALIASES = {"chi": "zho", "fre": "fra", "ger": "deu", "dut": "nld"}


def audio_tag_fix(meta):
    """The tag the transcribed audio stream should carry, when its current one is missing or wrong; else None."""
    want = LANG3.get(meta["lang"])
    have = meta["audio"][meta.get("audio_stream", 0)].get("language")
    return want if want and LANG3_ALIASES.get(have, have) != want else None


# Characters only the source language uses. On-screen text without them (clothing, props, misreads) is left out of
# the sheets. Latin-script languages have no such test and keep everything.
SOURCE_SCRIPT = {
    "ja": r"[぀-ヿ一-鿿]", "zh": r"[一-鿿]", "yue": r"[一-鿿]",
    "ko": r"[가-힣ᄀ-ᇿ]", "ru": r"[Ѐ-ӿ]", "uk": r"[Ѐ-ӿ]",
    "ar": r"[؀-ۿ]", "he": r"[֐-׿]", "th": r"[฀-๿]", "hi": r"[ऀ-ॿ]",
}


def second_model(lang):
    """The second transcription model to use for a language, if it has been downloaded."""
    for name in (SECOND_MODEL.get(lang), SECOND_FALLBACK):
        if name and (MODELS / name / "model.bin").exists():
            return name
    return None


def load_meta(work):
    return json.loads((Path(work) / "meta.json").read_text(encoding="utf-8"))


def save_meta(work, meta):
    (Path(work) / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")


def count_frames(video, stream):
    """Frames a decoder actually shows. Packet counts can be higher: an MP4 cut without re-encoding keeps hidden
    packets before its first frame. Decoding takes about 20 s per 30 minutes of 1080p."""
    cmd = ["ffmpeg", "-hide_banner", "-nostdin", "-v", "error", "-nostats", "-progress", "pipe:1", "-i", str(video),
           "-map", f"0:{stream}", "-fps_mode", "passthrough", "-f", "null", "-"]
    out = subprocess.run(cmd, capture_output=True, text=True, check=True).stdout
    return int([line for line in out.splitlines() if line.startswith("frame=")][-1].split("=")[1])


def grab_png(video, frame, meta, stream):
    """One exact frame, counted from the first video frame, as PNG bytes in true colour. stream is an ffmpeg stream
    specifier such as "3" (the source's video stream index) or "v:0"."""
    frame = min(max(0, frame), meta["frames"] - 1)  # a time at the very end rounds past the last frame
    t = max(0.0, meta.get("video_offset", 0.0) + (frame - 0.5) / meta["fps"])
    cmd = [
        "ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error", "-ss", f"{t:.6f}", "-i", str(video),
        "-map", f"0:{stream}", "-frames:v", "1", "-vf", f"scale=in_color_matrix={meta['matrix']},format=rgb24",
        "-f", "image2pipe", "-vcodec", "png", "-",
    ]
    return subprocess.run(cmd, capture_output=True, check=True).stdout
