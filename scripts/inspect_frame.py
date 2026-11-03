"""Helps place a sign. Saves the exact frame at a time as a PNG in true colour (unlike the JPEGs in frames/, which
shift colours), lists the text boxes OCR found at that moment in pixels, and prints the colour at any points named.
Usage: inspect_frame.py <workdir> <seconds> [--px x,y [x,y ...]]
Open the PNG it names with the Read tool to see the frame."""
import argparse
import io
import json
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as cm

ap = argparse.ArgumentParser()
ap.add_argument("work")
ap.add_argument("seconds", type=float)
ap.add_argument("--px", nargs="*", default=[])
args = ap.parse_args()

work = Path(args.work).resolve()
meta = cm.load_meta(work)
W, H = meta["width"], meta["height"]
frame = min(int(round(args.seconds * meta["fps"])), meta["frames"] - 1)  # the end rounds past the last frame
img = Image.open(io.BytesIO(cm.grab_png(meta["source"], frame, meta, str(meta["video_stream"])))).convert("RGB")
out = work / "survey" / f"frame_{args.seconds:.2f}.png"
img.save(out)
print(f"frame {frame} at {frame / meta['fps']:.3f}s, {W}x{H} -> {out}")

wanted = f"{int(round(args.seconds * 2)) + 1:05d}.jpg"  # the OCR frame nearest this moment
ocr = work / "ocr" / "ocr.jsonl"
if ocr.exists():
    for line in open(ocr, encoding="utf-8"):
        record = json.loads(line)
        if record["file"] == wanted:
            print(f"OCR text at {(int(wanted[:5]) - 1) / 2:.1f}s (x0,y0 to x1,y1 in pixels):")
            for b in record["boxes"]:
                x0, y0 = round(b["x"] * W), round(b["y"] * H)
                x1, y1 = round((b["x"] + b["w"]) * W), round((b["y"] + b["h"]) * H)
                print(f"  {x0:5d},{y0:5d} to {x1:5d},{y1:5d}  conf {b['conf']:.2f}  {b['text']}")
            break
for p in args.px:
    px, py = (int(v) for v in p.split(","))
    patch = [img.getpixel((min(W - 1, max(0, px + dx)), min(H - 1, max(0, py + dy))))
             for dx in (-2, 0, 2) for dy in (-2, 0, 2)]
    avg = tuple(round(sum(c[i] for c in patch) / len(patch)) for i in range(3))
    print(f"colour at {px},{py}: {img.getpixel((px, py))}, average of the 5x5 area around it {avg}")
