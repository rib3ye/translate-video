"""Speech-to-text for the work folder's audio (prepare.py runs it).
  asr.py mlx <wav> <model_dir> <out.json> --lang ja          Whisper on the Apple GPU, with word timings
  asr.py ct2 <wav> <model_dir> <out.json> --lang ja [--chunk-length 15]
                                                             faster-whisper on the CPU, the second opinion
  asr.py detect <wav> <model_dir>                            print the language Whisper hears most"""
import argparse
import json
import time
import wave
from collections import Counter

import numpy as np

ap = argparse.ArgumentParser()
ap.add_argument("engine", choices=["mlx", "ct2", "detect"])
ap.add_argument("wav")
ap.add_argument("model_dir")
ap.add_argument("out", nargs="?")
ap.add_argument("--lang")
ap.add_argument("--chunk-length", type=int, default=30)
args = ap.parse_args()
t0 = time.time()


def read_wav(path):
    # faster-whisper's own file loader breaks on the installed PyAV version, so read the 16 kHz mono WAV here.
    with wave.open(path, "rb") as fh:
        return np.frombuffer(fh.readframes(fh.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0


if args.engine == "detect":
    import mlx_whisper

    audio = read_wav(args.wav)
    votes = Counter()
    for frac in (0.2, 0.5, 0.8):  # three 30-second windows, so an opening song can't decide it
        start = int(len(audio) * frac)
        clip = audio[start : start + 16000 * 30]
        result = mlx_whisper.transcribe(clip, path_or_hf_repo=args.model_dir, language=None, verbose=None)
        votes[result["language"]] += 1
    print(votes.most_common(1)[0][0])
elif args.engine == "mlx":
    import mlx_whisper

    result = mlx_whisper.transcribe(
        args.wav,
        path_or_hf_repo=args.model_dir,
        language=args.lang,
        task="transcribe",
        word_timestamps=True,
        condition_on_previous_text=False,  # stops one bad guess from repeating through the rest of the video
        hallucination_silence_threshold=2.0,
        temperature=(0.0, 0.2, 0.4, 0.6, 0.8, 1.0),
        verbose=False,
    )
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False)
    print(f"whisper: {len(result['segments'])} segments in {time.time() - t0:.0f}s")
else:
    from faster_whisper import WhisperModel

    model = WhisperModel(args.model_dir, device="cpu", compute_type="float32", cpu_threads=8)
    segments, _ = model.transcribe(
        read_wav(args.wav),
        language=args.lang,
        chunk_length=args.chunk_length,
        condition_on_previous_text=False,
        beam_size=5,  # no word timings: they crash Kotoba, and Whisper supplies the timing anyway
    )
    rows = []
    for seg in segments:
        rows.append(
            {"start": seg.start, "end": seg.end, "text": seg.text, "no_speech_prob": seg.no_speech_prob,
             "avg_logprob": seg.avg_logprob}
        )
        if len(rows) % 100 == 0:
            print(f"second model: {len(rows)} segments, audio position {seg.end:.0f}s", flush=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump({"segments": rows}, fh, ensure_ascii=False)
    print(f"second model: {len(rows)} segments in {time.time() - t0:.0f}s")
