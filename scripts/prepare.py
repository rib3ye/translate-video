"""Gets a video ready to translate. Its work folder receives meta.json (facts about the video), audio for
speech-to-text, two frames a second, camera cuts, on-screen text read by Apple's OCR, one or two transcripts, and the
section sheets you translate from. Each step skips itself when its output exists, so re-running resumes after a
failure. Steps, in order: probe audio frames cuts ocr asr sheets.

Usage: prepare.py <video> --lang ja|auto [--work DIR] [--only probe,cuts] [--redo ocr,sheets]
                  [--audio-stream N] [--keep-latin "KAI,SORA"]
--only runs just those steps (probe,cuts is all an existing SRT needs); --redo reruns finished ones.
--keep-latin names Latin-script words to keep in the sheets of a non-Latin source (names shown on screen).
The last line printed is the work folder."""
import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import time
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as cm

STEPS = ["probe", "audio", "frames", "cuts", "ocr", "asr", "sheets"]
FF = ["ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error", "-y"]

ap = argparse.ArgumentParser()
ap.add_argument("video")
ap.add_argument("--lang", required=True, help="source language as a Whisper code (ja, ko, zh, es, ...) or auto")
ap.add_argument("--work")
ap.add_argument("--only", default="")
ap.add_argument("--redo", default="")
ap.add_argument("--audio-stream", type=int, default=0, help="which audio stream to transcribe, counting from 0")
ap.add_argument("--keep-latin")
args = ap.parse_args()

video = Path(args.video).expanduser().resolve()
if not video.exists():
    raise SystemExit(f"no such file: {video}")
if args.work:
    work = Path(args.work).expanduser().resolve()
else:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", video.stem).strip("-")[-40:].strip("-") or "video"
    work = cm.WORK_ROOT / f"{slug}-{hashlib.sha1(str(video).encode()).hexdigest()[:6]}"
for sub in ("audio", "asr", "ocr", "survey", "sheets", "translation", "review"):
    (work / sub).mkdir(parents=True, exist_ok=True)
only = set(filter(None, args.only.split(","))) or set(STEPS)
redo = set(filter(None, args.redo.split(",")))
if (only | redo) - set(STEPS):
    raise SystemExit(f"unknown steps {sorted((only | redo) - set(STEPS))}; the steps are {STEPS}")


def wanted(step, output):
    return step in only and (step in redo or not Path(output).exists())


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def ffprobe(*a):
    cmd = ["ffprobe", "-v", "error", *a, str(video)]
    return subprocess.run(cmd, capture_output=True, text=True, check=True).stdout


# probe: the facts every later step relies on
meta_path = work / "meta.json"
if wanted("probe", meta_path):
    log("probe")
    info = json.loads(ffprobe(
        "-show_entries",
        "format=duration,start_time:stream=index,codec_type,codec_name,width,height,pix_fmt,r_frame_rate,"
        "avg_frame_rate,start_time,color_space,color_transfer,color_primaries,color_range,channels"
        ":stream_disposition=attached_pic:stream_tags=language",
        "-of", "json",
    ))
    streams = info["streams"]
    videos = [s for s in streams if s["codec_type"] == "video" and not s.get("disposition", {}).get("attached_pic")]
    audios = [s for s in streams if s["codec_type"] == "audio"]
    if not videos or not audios:
        raise SystemExit("the file needs both a video and an audio stream")
    v = videos[0]
    nominal = Fraction(v["r_frame_rate"])
    average = Fraction(v["avg_frame_rate"]) if v.get("avg_frame_rate", "0/0") != "0/0" else nominal
    rate = nominal if 0 < nominal <= 120 else average
    log("counting frames")
    counted = cm.count_frames(video, v["index"])
    file_start = float(info["format"].get("start_time") or 0)
    video_start = float(v.get("start_time") or file_start)
    space = v.get("color_space") or "unknown"
    meta = {
        "source": str(video),
        "lang": args.lang,
        "width": v["width"],
        "height": v["height"],
        "fps": float(rate),
        "fps_fraction": f"{rate.numerator}/{rate.denominator}",
        "frames": counted,
        "duration": float(info["format"]["duration"]),
        "video_stream": v["index"],
        "video_codec": v.get("codec_name"),
        "pix_fmt": v.get("pix_fmt"),
        # the YCbCr matrix overlays are converted with: what the file says, else what players assume for its size
        "matrix": "bt601" if space in ("smpte170m", "bt470bg") or (space == "unknown" and v["height"] < 720) else "bt709",
        "color": {k: v.get(k) for k in ("color_space", "color_transfer", "color_primaries", "color_range")},
        "video_offset": round(video_start - file_start, 6),
        "audio": [
            {"index": a["index"], "codec": a.get("codec_name"), "language": (a.get("tags") or {}).get("language"),
             "channels": a.get("channels"), "offset": round(float(a.get("start_time") or file_start) - video_start, 6)}
            for a in audios
        ],
        "audio_stream": args.audio_stream,
        "keep_latin": [],
        "max_line": 42 if v["width"] >= v["height"] else 32,
        "max_cps": 20.0,
        "timeline": "every time in this folder is seconds from the first video frame",
    }
    warnings = []
    if abs(float(average) - float(rate)) / float(rate) > 0.002:
        warnings.append(
            f"variable frame rate (nominal {float(rate):.3f} fps, average {float(average):.3f}): timing assumes a constant"
            f" rate, so convert first: ffmpeg -i IN -fps_mode cfr -r {meta['fps_fraction']} -c:a copy OUT")
    if meta["color"]["color_transfer"] in ("smpte2084", "arib-std-b67"):
        warnings.append("HDR video: burn.py refuses it; tone-map to SDR first")
    for a in meta["audio"]:
        if abs(a["offset"]) > 0.1:
            warnings.append(f"audio stream {a['index']} starts {a['offset']:+.3f}s from the video; audio.wav is shifted to match")
    meta["warnings"] = warnings
    cm.save_meta(work, meta)
meta = cm.load_meta(work)
for w in meta.get("warnings", []):
    log("WARNING " + w)
if args.lang != "auto" and meta["lang"] != args.lang:
    meta["lang"] = args.lang
if args.keep_latin is not None:
    meta["keep_latin"] = [w.strip() for w in args.keep_latin.split(",") if w.strip()]
cm.save_meta(work, meta)

# audio: 16 kHz mono, lined up so that second 0 of the WAV is the first video frame
wav = work / "audio" / "mono16k.wav"
if wanted("audio", wav):
    log("audio")
    a = meta["audio"][meta["audio_stream"]]
    d = a["offset"]
    shift = []
    if d > 0.02:
        shift = ["-af", f"adelay=delays={int(round(d * 1000))}:all=1"]
    elif d < -0.02:
        shift = ["-af", f"asetpts=PTS-STARTPTS,atrim=start={-d:.3f}"]
    tmp = wav.with_suffix(".tmp.wav")
    subprocess.run(FF + ["-i", str(video), "-map", f"0:{a['index']}", "-ac", "1", "-ar", "16000", *shift,
                         "-c:a", "pcm_s16le", str(tmp)], check=True)
    tmp.rename(wav)

main_model = cm.MODELS / cm.MAIN_MODEL
if meta["lang"] == "auto":
    if not (main_model / "weights.npz").exists() or not wav.exists():
        raise SystemExit("--lang auto needs the Whisper model and the audio step: pass the spoken language instead")
    log("detecting the language")
    found = subprocess.run([str(cm.PYTHON), "-I", "-B", str(cm.SCRIPTS / "asr.py"), "detect", str(wav), str(main_model)],
                           capture_output=True, text=True, check=True).stdout.split()[-1]
    meta["lang"] = found
    cm.save_meta(work, meta)
    log(f"language: {found}")
if meta["lang"] != "auto" and cm.audio_tag_fix(meta):
    have = meta["audio"][meta["audio_stream"]].get("language") or "nothing"
    log(f"NOTE the audio's language tag says {have} but the speech is {meta['lang']}: burn.py will tag it "
        f"{cm.audio_tag_fix(meta)} unless told --audio-lang keep")

# frames: two a second, for OCR and the contact sheets (never for measuring colour: JPEGs shift it)
frames_dir = work / "frames"
fresh = set()  # steps that ran this time, so the sheets get rebuilt from their new output
if wanted("frames", frames_dir):
    fresh.add("frames")
    log("frames")
    tmp = work / "frames.tmp"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir()
    subprocess.run(FF + ["-i", str(video), "-map", f"0:{meta['video_stream']}", "-vf", "fps=2", "-q:v", "3",
                         str(tmp / "%05d.jpg")], check=True)
    shutil.rmtree(frames_dir, ignore_errors=True)
    tmp.rename(frames_dir)

background = []  # (name, process, temporary output, final output)

# cuts: camera cuts, which subtitles snap to
cuts_path = work / "survey" / "cuts.txt"
if wanted("cuts", cuts_path):
    log("cuts (in the background)")
    proc = subprocess.Popen(FF + ["-i", str(video), "-map", f"0:{meta['video_stream']}", "-an", "-vf",
                                  "scale=480:-2,select='gt(scene,0.22)',metadata=print:file=cuts_raw.txt", "-f", "null",
                                  "-"], cwd=work / "survey")
    background.append(("cuts", proc, None, cuts_path))

# asr: Whisper on the GPU and, when there is one, the second model on the CPU, both in the background
whisper_out, second_out = work / "asr" / "whisper.json", work / "asr" / "second.json"
if "asr" in only:
    if not (main_model / "weights.npz").exists():
        raise SystemExit("the Whisper model is missing: run get_models.py first")
    jobs = []
    if wanted("asr", whisper_out):
        jobs.append(("whisper", ["mlx", str(wav), str(main_model)], whisper_out))
    second = cm.second_model(meta["lang"])
    if second and wanted("asr", second_out):
        jobs.append(("second", ["ct2", str(wav), str(cm.MODELS / second)], second_out))
    elif not second:
        log("no second model for this language: the sheets will have Whisper only")
    for name, head, out in jobs:
        tmp = out.with_suffix(".tmp")
        extra = ["--chunk-length", str(cm.CHUNK_LENGTH.get(second, 30))] if name == "second" else []
        cmd = [str(cm.PYTHON), "-I", "-B", str(cm.SCRIPTS / "asr.py"), *head, str(tmp), "--lang", meta["lang"], *extra]
        log(f"{name} transcript (in the background, log in asr/{name}.log)")
        proc = subprocess.Popen(cmd, stdout=open(work / "asr" / f"{name}.log", "w"), stderr=subprocess.STDOUT)
        background.append((name, proc, tmp, out))

# ocr: on-screen text, while the transcripts run
ocr_path, tracks_path = work / "ocr" / "ocr.jsonl", work / "ocr" / "tracks.json"
if wanted("ocr", ocr_path):
    log("ocr")
    langs = cm.OCR_LANGS.get(meta["lang"], ["en-US"])
    tmp = ocr_path.with_suffix(".tmp")
    subprocess.run([str(cm.BIN / "ocr"), str(frames_dir), str(tmp), ",".join(langs)], check=True)
    tmp.rename(ocr_path)
    fresh.add("ocr")
if "ocr" in only and ocr_path.exists() and ("ocr" in fresh or not tracks_path.exists()):
    import ocr_tracks

    ocr_tracks.build(ocr_path, tracks_path)

failed = []
for name, proc, tmp, out in background:
    if proc.wait() != 0:
        failed.append(name)
        continue
    if name == "cuts":
        raw = (work / "survey" / "cuts_raw.txt").read_text()
        times = [float(t) - meta["video_offset"] for t in re.findall(r"pts_time:([0-9.]+)", raw)]
        cuts_path.write_text("".join(f"{t:.6f}\n" for t in times))
        log(f"cuts: {len(times)}")
    else:
        tmp.rename(out)
        fresh.add("asr")
        log(f"{name} transcript done")
if failed:
    raise SystemExit(f"failed: {failed}; see the logs in {work / 'asr'}, then re-run to resume")

# sheets: what you translate from
first_sheet = work / "sheets" / "section_00.txt"
if "sheets" in only and whisper_out.exists() and (wanted("sheets", first_sheet) or fresh):
    import build_sheets

    build_sheets.build(work)

summary = [f"{meta['duration'] / 60:.1f} min", f"{meta['width']}x{meta['height']}", f"{meta['fps']:.3f} fps",
           f"{meta['frames']} frames", f"language {meta['lang']}"]
if whisper_out.exists():
    summary.append(f"whisper {len(json.loads(whisper_out.read_text(encoding='utf-8'))['segments'])} segments")
if second_out.exists():
    summary.append(f"second {len(json.loads(second_out.read_text(encoding='utf-8'))['segments'])} segments")
log("done: " + ", ".join(summary))
print(work)
