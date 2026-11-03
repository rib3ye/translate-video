"""Merges the transcripts and on-screen text into one timeline per section (sheets/section_NN.txt), and makes a
labelled contact sheet of frames for each section (sheets/section_NN.jpg). prepare.py runs it; run it again after
changing --keep-latin. Usage: build_sheets.py <workdir> [section_seconds]"""
import json
import math
import re
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as cm
import ocr_tracks

LEGEND = (
    "# W = Whisper (best timing; [367.1] marks a pause at 367.1 s; ? = Whisper itself unsure)  S = second transcript\n"
    "# T/C/L/O = on-screen text at the bottom / top right / top left / elsewhere; @(x,y) = its top-left corner as\n"
    "# fractions of the frame. All times are seconds from the start of the video."
)
LABELS = {"bottom": "T", "topright": "C", "topleft": "L", "other": "O"}


def mmss(t):
    return f"{int(t // 60):02d}:{t % 60:04.1f}"


def whisper_line(seg):
    """Whisper text with a time marker at each pause, so a long line can be split into several subtitles."""
    words = seg.get("words") or []
    if not words:
        return seg["text"].strip()
    parts, last_mark, prev_end = [], words[0]["start"], words[0]["start"]
    for i, w in enumerate(words):
        if i and (w["start"] - prev_end > 0.25 or w["start"] - last_mark > 2.5):
            parts.append(f"[{w['start']:.1f}]")
            last_mark = w["start"]
        word = w["word"]
        parts.append(word if i and word.startswith(" ") else word.strip())  # keeps the spaces of spaced languages
        prev_end = w["end"]
    return "".join(parts).strip()


def build(work, section=180):
    work = Path(work)
    meta = cm.load_meta(work)
    out_dir = work / "sheets"
    out_dir.mkdir(exist_ok=True)
    for old in out_dir.glob("section_*"):
        old.unlink()
    whisper = json.loads((work / "asr/whisper.json").read_text(encoding="utf-8"))["segments"]
    second_path, tracks_path = work / "asr/second.json", work / "ocr/tracks.json"
    second = json.loads(second_path.read_text(encoding="utf-8"))["segments"] if second_path.exists() else []
    tracks = json.loads(tracks_path.read_text(encoding="utf-8")) if tracks_path.exists() else []
    script = cm.SOURCE_SCRIPT.get(meta["lang"])
    keep = set(meta.get("keep_latin", []))

    rows = []
    for s in whisper:
        text = whisper_line(s)
        if text:
            flag = " ?" if s.get("no_speech_prob", 0) > 0.6 or s.get("avg_logprob", 0) < -1.0 else ""
            rows.append((s["start"], 0, f"W {s['start']:.1f}-{s['end']:.1f}{flag}  {text}"))
    for s in second:
        if s["text"].strip():
            rows.append((s["start"], 1, f"S {s['start']:.1f}-{s['end']:.1f}  {s['text'].strip()}"))
    tracks = [t for t in tracks if not script or re.search(script, t["text"]) or t["text"] in keep]  # drops props
    for t, note in ocr_tracks.for_sheets(tracks, meta["duration"]):
        label = LABELS[t["region"]]
        rows.append((t["start"], 2,
                     f"{label} {t['start']:.1f}-{t['end']:.1f} @({t['x']:.2f},{t['y']:.2f})  {t['text']}  {note}".rstrip()))
    rows.sort(key=lambda r: (r[0], r[1]))

    n_sections = max(1, math.ceil(meta["duration"] / section))
    for i in range(n_sections):
        a, b = i * section, (i + 1) * section
        lines = [r[2] for r in rows if a <= r[0] < b]
        head = f"### section {i:02d}: {mmss(a)} to {mmss(min(b, meta['duration']))}\n{LEGEND}\n"
        (out_dir / f"section_{i:02d}.txt").write_text(head + "\n".join(lines) + "\n", encoding="utf-8")

    # Contact sheets: 36 frames spread over each section (one every 5 s for a full 3-minute section), labelled in
    # seconds. frames/ holds all of them, two a second, for a closer look.
    if not (work / "frames").exists():
        print(f"sheets: {n_sections} sections of {section}s, {len(rows)} rows; no frames/, so no contact sheets "
              "(prepare.py --redo frames brings them back)")
        return n_sections
    font = ImageFont.truetype(cm.FONT_FILE, 22, index=cm.FONT_MEDIUM)
    cols, rows_n, tw = (6, 6, 320) if meta["width"] >= meta["height"] else (9, 4, 213)
    th = int(round(tw * meta["height"] / meta["width"]))
    for i in range(n_sections):
        sheet = Image.new("RGB", (cols * tw, rows_n * th), (0, 0, 0))
        draw = ImageDraw.Draw(sheet)
        span = min(section, meta["duration"] - i * section)
        for k in range(cols * rows_n):
            t = i * section + k * span / (cols * rows_n)
            path = work / "frames" / f"{int(t * 2) + 1:05d}.jpg"
            if not path.exists():
                continue
            x, y = (k % cols) * tw, (k // cols) * th
            sheet.paste(Image.open(path).resize((tw, th), Image.BILINEAR), (x, y))
            draw.rectangle((x, y, x + 74, y + 28), fill=(0, 0, 0))
            draw.text((x + 4, y + 1), f"{t:.0f}", font=font, fill=(255, 255, 0))
        sheet.save(out_dir / f"section_{i:02d}.jpg", quality=82)
    print(f"sheets: {n_sections} sections of {section}s, {len(rows)} rows")
    return n_sections


if __name__ == "__main__":
    build(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 180)
