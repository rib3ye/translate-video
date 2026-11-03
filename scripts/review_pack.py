"""Builds one time-ordered file with each English subtitle (E#n) next to every source row (W, S, T), for the
independent review. Usage: review_pack.py <workdir>  ->  review/review_pack.txt"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as cm
import ocr_tracks
import subs_lib as sl

work = Path(sys.argv[1]).resolve()
meta = sl.setup(work)
whisper = json.loads((work / "asr/whisper.json").read_text(encoding="utf-8"))["segments"]
second_path, tracks_path = work / "asr/second.json", work / "ocr/tracks.json"
second = json.loads(second_path.read_text(encoding="utf-8"))["segments"] if second_path.exists() else []
tracks = json.loads(tracks_path.read_text(encoding="utf-8")) if tracks_path.exists() else []
script = cm.SOURCE_SCRIPT.get(meta["lang"])
keep = set(meta.get("keep_latin", []))

rows = []
for s in whisper:
    if s["text"].strip():
        rows.append((s["start"], 1, f"  W {s['start']:.1f}-{s['end']:.1f} {s['text'].strip()}"))
for s in second:
    if s["text"].strip():
        rows.append((s["start"], 2, f"  S {s['start']:.1f}-{s['end']:.1f} {s['text'].strip()}"))
relisten = work / "asr" / "relisten.txt"  # targeted re-listens: RP with the prompt, RN without
if relisten.exists():
    for line in relisten.read_text(encoding="utf-8").splitlines():
        m = re.match(r"([PN]) ([\d.]+)-([\d.]+) (.*)", line)
        if m:
            rows.append((float(m.group(2)), 2.5, f"  R{m.group(1)} {m.group(2)}-{m.group(3)} {m.group(4)}"))
tracks = [t for t in tracks if not script or re.search(script, t["text"]) or t["text"] in keep]
for t, note in ocr_tracks.for_sheets(tracks, meta["duration"]):
    rows.append((t["start"], 3, f"  T {t['start']:.1f}-{t['end']:.1f} {t['text']} {note}".rstrip()))
cues = sl.build_cues(sl.load_rows(sorted((work / "translation").glob("part_*.tsv"))), sl.load_cuts(work / "survey/cuts.txt"))
for i, c in enumerate(cues, 1):
    rows.append((sl.f2t(c.start), 0, f"E#{i} {sl.f2t(c.start):.1f}-{sl.f2t(c.end):.1f} ({c.cps:.0f}cps) "
                                     f"{c.text.replace(chr(10), ' / ')}"))
rows.sort(key=lambda r: (r[0], r[1]))
out = work / "review" / "review_pack.txt"
out.parent.mkdir(exist_ok=True)
out.write_text("\n".join(r[2] for r in rows) + "\n", encoding="utf-8")
print(f"{len(cues)} subtitles, {len(rows)} rows -> {out}")
