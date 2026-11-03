"""Shows chosen moments as they will look, in one labelled image to open with the Read tool: exact source frames with
the rendered overlays on top, or, with --video, frames straight from a burned file.
Usage: qa_sheet.py <workdir> <out.jpg> <seconds> [<seconds> ...] [--video burned.mp4] [--cols 2]"""
import argparse
import io
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as cm

ap = argparse.ArgumentParser()
ap.add_argument("work")
ap.add_argument("out")
ap.add_argument("times", nargs="+", type=float)
ap.add_argument("--video")
ap.add_argument("--cols", type=int, default=2)
args = ap.parse_args()

work = Path(args.work).resolve()
meta = cm.load_meta(work)
spans = json.loads((work / "overlay/spans.json").read_text()) if not args.video else []
tw = 960 if args.cols <= 2 else 640
th = int(round(tw * meta["height"] / meta["width"]))
rows = (len(args.times) + args.cols - 1) // args.cols
sheet = Image.new("RGB", (args.cols * tw, rows * th))
draw = ImageDraw.Draw(sheet)
label_font = ImageFont.truetype(cm.FONT_FILE, 22, index=cm.FONT_MEDIUM)
for k, t in enumerate(args.times):
    frame = int(round(t * meta["fps"]))
    if args.video:
        png = cm.grab_png(args.video, frame, meta, "v:0")
    else:
        png = cm.grab_png(meta["source"], frame, meta, str(meta["video_stream"]))
    img = Image.open(io.BytesIO(png)).convert("RGBA")
    overlay = next((name for a, b, name, _ in spans if a <= frame < b), None)
    if overlay:
        img = Image.alpha_composite(img, Image.open(work / "overlay" / overlay).convert("RGBA"))
    x, y = (k % args.cols) * tw, (k // args.cols) * th
    sheet.paste(img.convert("RGB").resize((tw, th), Image.LANCZOS), (x, y))
    draw.rectangle((x, y, x + 96, y + 28), fill=(0, 0, 0))
    draw.text((x + 4, y + 1), f"{t:.1f}s", font=label_font, fill=(255, 255, 0))
sheet.save(args.out, quality=88)
print("saved", args.out)
