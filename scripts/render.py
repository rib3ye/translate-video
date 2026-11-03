"""Draws the subtitles and translated signs as full-frame transparent PNGs, one per distinct on-screen state, then
writes the timed list ffmpeg overlays them from (overlay/list.ffconcat), the spans for the checking scripts
(overlay/spans.json), the frames where a sign covers the strip verify.py checks (overlay/sign_patch.json), and the
dialogue-only SRT (translation/subs.srt). Prints any rule warnings.
Usage: render.py <workdir>"""
import json
import shutil
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as cm
import subs_lib as sl

work = Path(sys.argv[1]).resolve()
meta = sl.setup(work)
W, H = meta["width"], meta["height"]
SS = 2  # draw at twice the size, then shrink, for smooth edges
geo = sl.geometry(meta)
K = geo["scale"]
PX, PY, PW, PH = sl.check_patch(meta)
PATCH = (PX * SS, PY * SS, (PX + PW) * SS, (PY + PH) * SS)
BOX = (0, 0, 0, int(meta.get("box_alpha", 190)))
WHITE, BLACK = (255, 255, 255, 255), (0, 0, 0, 255)


def font(size, bold=False):
    return ImageFont.truetype(cm.FONT_FILE, max(1, int(round(size * SS))), index=cm.FONT_BOLD if bold else cm.FONT_MEDIUM)


SUB_FONT = font(geo["size"])


def line_height(f, factor):
    ascent, descent = f.getmetrics()
    return int((ascent + descent) * factor)


def draw_sub(draw, text):
    lines = text.split("\n")
    line_h = line_height(SUB_FONT, 1.06)
    pad_x, pad_y = 22 * K * SS, 7 * K * SS
    bottom = geo["bottom"] * SS
    top_text = bottom - pad_y - line_h * len(lines)
    widest = max(draw.textlength(line, font=SUB_FONT) for line in lines)
    cx = W * SS / 2
    draw.rounded_rectangle((cx - widest / 2 - pad_x, top_text - pad_y, cx + widest / 2 + pad_x, bottom),
                           radius=10 * K * SS, fill=BOX)
    for i, line in enumerate(lines):
        draw.text((cx - draw.textlength(line, font=SUB_FONT) / 2, top_text + i * line_h), line, font=SUB_FONT, fill=WHITE)


def draw_plate(draw, sign, text):
    """A filled box with centred text, made to cover an on-screen label."""
    st = STYLES[sign["style"]]
    x0, y0, x1, y1 = (v * SS for v in sign["rect"])
    lines = text.split("|")
    size, margin = sign["size"], 10 * SS
    f = font(size, st["bold"])
    widest = max(draw.textlength(line, font=f) for line in lines)
    extra = widest + 2 * margin - (x1 - x0)
    if extra > 0 and sign["grow"]:
        if sign["grow"] == "grow-left":
            x0 = max(0, x0 - extra)
        elif sign["grow"] == "grow-right":
            x1 = min(W * SS, x1 + extra)
        else:
            x0, x1 = max(0, x0 - extra / 2), min(W * SS, x1 + extra / 2)
    while max(draw.textlength(line, font=f) for line in lines) > (x1 - x0) - 2 * margin and size > 12:
        size -= 1
        f = font(size, st["bold"])
    border = int(round(st["border_w"] * SS)) if st["border"] else 0
    draw.rounded_rectangle((x0, y0, x1, y1), radius=st["radius"] * SS, fill=st["fill"], outline=st["border"], width=border)
    line_h = line_height(f, 1.04)
    y = (y0 + y1 - line_h * len(lines)) / 2
    stroke = int(round(st["outline_w"] * SS)) if st["outline"] else 0
    for i, line in enumerate(lines):
        x = (x0 + x1 - draw.textlength(line, font=f)) / 2
        draw.text((x, y + i * line_h), line, font=f, fill=st["text"], stroke_width=stroke, stroke_fill=st["outline"])


def draw_caption(draw, sign, text):
    """Outlined text with its top-left corner at x, y, for labels where the picture should stay visible."""
    st = STYLES[sign["style"]] if sign["style"] else None
    f = font(sign["size"], True)
    fill = st["text"] if st else WHITE
    outline = st["outline"] if st and st["outline"] else BLACK
    stroke = int(round((st["outline_w"] if st and st["outline"] else 3) * SS))
    line_h = line_height(f, 1.04)
    for i, line in enumerate(text.split("|")):
        draw.text((sign["x"] * SS, sign["y"] * SS + i * line_h), line, font=f, fill=fill, stroke_width=stroke,
                  stroke_fill=outline)


def draw_big(draw, sign, text):
    """Large outlined title text, centred across the frame."""
    f = font(sign["size"] or 62 * K, True)
    y = (sign["y"] if sign["y"] is not None else 690 / 1080 * H) * SS
    line_h = line_height(f, 1.04)
    for i, line in enumerate(text.split("|")):
        x = (W * SS - draw.textlength(line, font=f)) / 2
        draw.text((x, y + i * line_h), line, font=f, fill=WHITE, stroke_width=int(4 * K * SS), stroke_fill=BLACK)


DRAW = {"plate": draw_plate, "caption": draw_caption, "big": draw_big}

parts = sorted((work / "translation").glob("part_*.tsv"))
if not parts:
    raise SystemExit("no translation/part_*.tsv yet")
cues = sl.build_cues(sl.load_rows(parts), sl.load_cuts(work / "survey/cuts.txt"))
sign_rows, defined = sl.load_signs(work / "translation/signs.tsv")
STYLES = sl.styles_from(defined)
signs = []
for a, b, kind, text, lineno in sign_rows:
    try:
        signs.append((sl.t2f(a), sl.t2f(b), sl.parse_kind(kind, STYLES), text))
    except ValueError as e:
        raise SystemExit(f"signs.tsv:{lineno}: {e}")
problems = sl.check(cues)
sl.write_srt(cues, work / "translation/subs.srt")

total = meta["frames"]
events = sorted({0} | {c.start for c in cues} | {c.end for c in cues} | {s[0] for s in signs} | {s[1] for s in signs})
events = [e for e in events if 0 <= e < total] + [total]

out_dir = work / "overlay"
shutil.rmtree(out_dir, ignore_errors=True)
out_dir.mkdir()
cache, spans, covered = {}, [], []
for a, b in zip(events, events[1:]):
    active_cue = next((i for i, c in enumerate(cues) if c.start <= a < c.end), None)
    active_signs = tuple(i for i, s in enumerate(signs) if s[0] <= a < s[1])
    key = (active_cue, active_signs)
    if key not in cache:
        name = f"o{len(cache):05d}.png"
        layer = Image.new("RGBA", (W * SS, H * SS), (0, 0, 0, 0))
        draw = ImageDraw.Draw(layer)
        for i in active_signs:
            _, _, sign, text = signs[i]
            DRAW[sign["kind"]](draw, sign, text)
        # A sign inside verify.py's strip changes it whether or not a subtitle shows, so verify.py skips these frames
        under = bool(active_signs) and layer.getchannel("A").crop(PATCH).getbbox() is not None
        if active_cue is not None:
            draw_sub(draw, cues[active_cue].text)
        layer.resize((W, H), Image.LANCZOS).save(out_dir / name, compress_level=6)
        cache[key] = (name, under)
    name, under = cache[key]
    spans.append((a, b, name, key == (None, ())))
    if under:
        if covered and covered[-1][1] == a:
            covered[-1][1] = b
        else:
            covered.append([a, b])

# Each change sits half a frame before its frame. "framerate 1000000" gives every PNG a microsecond clock: by default
# each gets a 1/25 s clock, and the rounding to 40 ms steps puts subtitles a frame early at 29.97 fps and above.
concat = ["ffconcat version 1.0"]
for a, b, name, _ in spans:
    start = max(0.0, (a - 0.5) / sl.FPS)
    concat += [f"file '{name}'", "option framerate 1000000", f"duration {(b - 0.5) / sl.FPS - start:.6f}"]
concat += [f"file '{spans[-1][2]}'", "option framerate 1000000"]
(out_dir / "list.ffconcat").write_text("\n".join(concat) + "\n")
(out_dir / "spans.json").write_text(json.dumps(spans))
(out_dir / "sign_patch.json").write_text(json.dumps(covered))
print(f"{len(cues)} subtitles, {len(signs)} signs, {len(cache)} overlay images, {len(problems)} warnings")
for p in problems:
    print("  ", p)
