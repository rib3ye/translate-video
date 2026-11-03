"""Listens again to doubtful stretches, once with a prompt naming the show's people and vocabulary (P) and once
without (N). Write the prompt first, in the source language and script, to <workdir>/asr/prompt.txt: the show's
title, the cast's names, and recurring words. Prints the readings and appends them to asr/relisten.txt.
Usage: relisten.py <workdir> <start-end> [<start-end> ...]      times in seconds, e.g. 185-192"""
import sys
import wave
from pathlib import Path

import mlx_whisper
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as cm

work = Path(sys.argv[1]).resolve()
meta = cm.load_meta(work)
ranges = [tuple(float(x) for x in r.split("-")) for r in sys.argv[2:]]
with wave.open(str(work / "audio/mono16k.wav"), "rb") as fh:
    audio = np.frombuffer(fh.readframes(fh.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
prompt_path = work / "asr" / "prompt.txt"
prompt = prompt_path.read_text(encoding="utf-8").strip() if prompt_path.exists() else ""
model = str(cm.MODELS / cm.MAIN_MODEL)

lines = []
for a, b in ranges:
    clip = audio[int(a * 16000) : int(b * 16000)]
    lines.append(f"=== {a:.1f}-{b:.1f}")
    for tag, p in (("P", prompt), ("N", "")):
        if tag == "P" and not p:
            continue
        r = mlx_whisper.transcribe(clip, path_or_hf_repo=model, language=meta["lang"], task="transcribe",
                                   temperature=0.0, initial_prompt=p or None, condition_on_previous_text=False,
                                   word_timestamps=False, verbose=None)
        for s in r["segments"]:
            lines.append(f"{tag} {a + s['start']:.1f}-{a + s['end']:.1f} {s['text'].strip()}")
text = "\n".join(lines) + "\n"
print(text, end="")
with open(work / "asr" / "relisten.txt", "a", encoding="utf-8") as fh:
    fh.write(text)
