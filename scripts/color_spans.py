"""Finds the exact frames where a solid-colour graphic (a topic card, a lower-third bar) is on screen, by watching a
thin strip of the picture in every frame. Gives frame-exact start and end times for signs.tsv.
Usage: color_spans.py <workdir> --rect x,y,w,h --rgb r,g,b [--tol 22] [--min-px 150]
Measure the colour first with inspect_frame.py --px, and lay the strip (2 px tall is enough) across a plain part of
the graphic. Prints start and end seconds and the graphic's left and right edges inside the strip."""
import argparse
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as cm

ap = argparse.ArgumentParser()
ap.add_argument("work")
ap.add_argument("--rect", required=True)
ap.add_argument("--rgb", required=True)
ap.add_argument("--tol", type=int, default=22, help="how far each channel may stray from the colour")
ap.add_argument("--min-px", type=int, default=150, help="matching pixels needed across the strip")
args = ap.parse_args()

work = Path(args.work).resolve()
meta = cm.load_meta(work)
x, y, w, h = (int(v) // 2 * 2 for v in args.rect.split(","))  # 4:2:0 video crops at even sizes only
w, h = max(w, 2), max(h, 2)
target = np.array([int(v) for v in args.rgb.split(",")], np.int16)
cmd = ["ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error", "-i", meta["source"], "-map",
       f"0:{meta['video_stream']}", "-an", "-vf", f"crop={w}:{h}:{x}:{y},scale=in_color_matrix={meta['matrix']},format=rgb24",
       "-fps_mode", "passthrough", "-f", "rawvideo", "-"]
proc = subprocess.Popen(cmd, stdout=subprocess.PIPE)
size, hits, n = w * h * 3, [], 0
while True:
    buf = proc.stdout.read(size)
    if len(buf) < size:
        break
    row = np.frombuffer(buf, dtype=np.uint8).reshape(h, w, 3).astype(np.int16).mean(axis=0)
    xs = np.flatnonzero((np.abs(row - target) <= args.tol).all(axis=1))
    if xs.size >= args.min_px:
        hits.append((n, int(xs.min()) + x, int(xs.max()) + x))
    n += 1
proc.wait()

runs, cur = [], None
for f, left, right in hits:
    if cur and f - cur["end"] <= 3:  # bridge a misread frame or two
        cur["end"] = f
        cur["lefts"].append(left)
        cur["rights"].append(right)
    else:
        cur = {"start": f, "end": f, "lefts": [left], "rights": [right]}
        runs.append(cur)
rows = []
for r in runs:
    if r["end"] - r["start"] < 6:
        continue  # a flash, not a graphic
    rows.append({"start": round(r["start"] / meta["fps"], 3), "end": round((r["end"] + 1) / meta["fps"], 3),
                 "left": int(np.median(r["lefts"])), "right": int(np.median(r["rights"]))})
out = work / "survey" / f"spans_{x}_{y}.json"
out.write_text(json.dumps(rows, indent=0))
print(f"{n} frames read, {len(rows)} appearances -> {out}")
for r in rows:
    print(f"{r['start']:9.3f} {r['end']:9.3f}   x {r['left']}..{r['right']}")
