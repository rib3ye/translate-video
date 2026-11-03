"""Shared subtitle logic: reads the translation files, wraps lines, fits timing to subtitle standards, parses signs,
writes SRT. Call setup(work) before anything else: it sets the frame rate and line rules from meta.json.

Part files (translation/part_NN.tsv), one row per subtitle, tab separated:
    start_seconds <TAB> end_seconds <TAB> text
"|" in the text forces a line break; "-Line one|-Line two" is two speakers; lines starting with # are comments.

Signs file (translation/signs.tsv):
    start <TAB> end <TAB> kind <TAB> text          kinds: plate, caption, big (see references/signs.md)
    @style <name> fill=#RRGGBB[AA] border=#RRGGBB:width text=#RRGGBB outline=#RRGGBB:width radius=N bold=0|1
"""
import bisect
import json
import re
from dataclasses import dataclass
from pathlib import Path

FPS = None  # set by setup()
TOTAL = None  # frames in the video, set by setup()
MAX_LINE = 42
MAX_CPS = 20.0
MIN_SECONDS = 5 / 6
MAX_SECONDS = 7.0
GAP_FRAMES = 2
LINGER_SECONDS = 1 / 3  # extra time on screen after the speech ends, when there is room
CLOSE_GAP_SECONDS = 0.5  # a smaller gap than this closes to GAP_FRAMES, which reads more smoothly
SNAP_START = (0.25, 1 / 3)  # look this far before and after a subtitle's start for a camera cut to start on
SNAP_END = (1 / 3, 0.42)
EARLY_START = 1 / 3  # how much earlier a too-fast subtitle may start

NO_BREAK_AFTER = set(
    """a an the of to in on at for with by from and or but so that this these those my your his her their our its
    i you we he she they it is are was were be been am do does did not no if as than then who what when where why how
    just really very like about would could should will can have has had get got i'm you're we're they're he's she's
    it's that's don't didn't can't won't""".split()
)

BUILTIN_STYLES = {
    "box": "fill=#000000BE",  # the subtitle box
    "black": "fill=#000000EB border=#EBEBEB:2",
    "gold": "fill=#000000 border=#CDA53C:2",
    "red": "fill=#BE1E32",
    "pink": "fill=#AA1E78 border=#28286E:2",
    "white": "fill=#FFFFFF text=#000000",
}


def setup(work):
    """Loads meta.json and sets the frame rate and line rules from it. Returns the meta."""
    global FPS, TOTAL, MAX_LINE, MAX_CPS
    meta = json.loads((Path(work) / "meta.json").read_text(encoding="utf-8"))
    FPS = meta["fps"]
    TOTAL = meta["frames"]
    MAX_LINE = meta.get("max_line", 42)
    MAX_CPS = meta.get("max_cps", 20.0)
    return meta


def geometry(meta):
    """Subtitle size and placement, scaled from the 1080p design. meta.json keys sub_size and sub_bottom (pixels)
    override them."""
    scale = min(meta["width"], meta["height"]) / 1080
    return {
        "scale": scale,
        "size": meta.get("sub_size", 48 * scale),
        "bottom": meta.get("sub_bottom", meta["height"] - 34 * scale),
    }


def frames(seconds):
    return int(round(seconds * FPS))


@dataclass
class Cue:
    start: int  # frames
    end: int  # frames, exclusive
    text: str  # wrapped, with \n between lines
    raw: str = ""

    @property
    def seconds(self):
        return (self.end - self.start) / FPS

    @property
    def cps(self):
        return len(self.text.replace("\n", "")) / max(self.seconds, 0.001)


def wrap(text):
    """Breaks text into at most two lines of up to MAX_LINE characters, at the most natural point."""
    if "|" in text:
        return "\n".join(p.strip() for p in text.split("|"))
    if len(text) <= MAX_LINE:
        return text
    if text.startswith("-") and " -" in text:  # two speakers: one line each
        i = text.index(" -")
        return text[:i] + "\n" + text[i + 1 :]
    words = text.split(" ")
    best, best_cost = None, 1e9
    for i in range(1, len(words)):
        a, b = " ".join(words[:i]), " ".join(words[i:])
        if len(a) > MAX_LINE or len(b) > MAX_LINE:
            continue
        cost = abs(len(a) - len(b))
        if words[i - 1].lower().strip("\"'") in NO_BREAK_AFTER:
            cost += 14
        if re.search(r"[,.?!:;—]$", words[i - 1]):
            cost -= 18
        if len(a) > len(b):
            cost += 2  # a longer bottom line sits better on screen
        if cost < best_cost:
            best, best_cost = a + "\n" + b, cost
    return best if best else text


def t2f(t):
    return int(round(float(t) * FPS))


def f2t(f):
    return f / FPS


def load_rows(paths):
    rows = []
    for path in paths:
        for lineno, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip() or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) != 3:
                raise ValueError(f"{Path(path).name}:{lineno}: expected start, end and text separated by tabs: {line!r}")
            rows.append((float(parts[0]), float(parts[1]), parts[2].strip()))
    rows.sort(key=lambda r: r[0])
    return rows


def load_cuts(path):
    path = Path(path)
    return sorted(t2f(x) for x in path.read_text().split()) if path.exists() else []


def load_signs(path):
    """Returns (rows, style definitions); rows are (start, end, kind, text, line number)."""
    rows, styles = [], {}
    path = Path(path)
    if not path.exists():
        return rows, styles
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip() or line.startswith("#"):
            continue
        if line.startswith("@style"):
            parts = line.split(None, 2)
            if len(parts) < 2:
                raise ValueError(f"signs.tsv:{lineno}: @style needs a name")
            styles[parts[1]] = parts[2] if len(parts) > 2 else ""
            continue
        parts = line.split("\t")
        if len(parts) != 4:
            raise ValueError(f"signs.tsv:{lineno}: expected start, end, kind and text separated by tabs: {line!r}")
        rows.append((float(parts[0]), float(parts[1]), parts[2].strip(), parts[3].strip(), lineno))
    return rows, styles


def hex_rgba(value):
    v = value.lstrip("#")
    if len(v) not in (6, 8) or not re.fullmatch(r"[0-9A-Fa-f]+", v):
        raise ValueError(f"bad colour {value!r}: use #RRGGBB or #RRGGBBAA")
    return tuple(int(v[i : i + 2], 16) for i in range(0, len(v), 2)) + ((255,) if len(v) == 6 else ())


def parse_style(spec):
    st = {"fill": (0, 0, 0, 190), "border": None, "border_w": 0.0, "text": (255, 255, 255, 255), "outline": None,
          "outline_w": 0.0, "radius": 4.0, "bold": True}
    for item in spec.split():
        key, _, val = item.partition("=")
        if key in ("fill", "text"):
            st[key] = hex_rgba(val)
        elif key in ("border", "outline"):
            colour, _, width = val.partition(":")
            st[key], st[key + "_w"] = hex_rgba(colour), float(width or 2)
        elif key == "radius":
            st["radius"] = float(val)
        elif key == "bold":
            st["bold"] = val not in ("0", "no", "false")
        else:
            raise ValueError(f"unknown style setting {key!r} in {spec!r}")
    return st


def styles_from(defined):
    styles = {name: parse_style(spec) for name, spec in BUILTIN_STYLES.items()}
    styles.update({name: parse_style(spec) for name, spec in defined.items()})
    return styles


def parse_kind(kind, styles):
    """Checks a sign kind and returns its settings. Coordinates and sizes are in the video's own pixels."""
    name, *p = kind.split(":")
    try:
        if name == "plate":
            if len(p) not in (6, 7):
                raise ValueError("plate needs x0:y0:x1:y1:size:style[:grow|grow-left|grow-right]")
            x0, y0, x1, y1, size = (float(v) for v in p[:5])
            grow = p[6] if len(p) == 7 else ""
            if grow not in ("", "grow", "grow-left", "grow-right"):
                raise ValueError(f"unknown plate growth {grow!r}")
            if x1 <= x0 or y1 <= y0:
                raise ValueError("plate corners must be top-left then bottom-right")
            style = p[5]
            sign = {"kind": "plate", "rect": (x0, y0, x1, y1), "size": size, "style": style, "grow": grow}
        elif name == "caption":
            if len(p) not in (3, 4):
                raise ValueError("caption needs x:y:size[:style]")
            style = p[3] if len(p) == 4 else None
            sign = {"kind": "caption", "x": float(p[0]), "y": float(p[1]), "size": float(p[2]), "style": style}
        elif name == "big":
            style = None
            sign = {"kind": "big", "y": float(p[0]) if p else None, "size": float(p[1]) if len(p) > 1 else None}
        else:
            raise ValueError(f"unknown sign kind {name!r} (plate, caption or big)")
    except ValueError as e:
        raise ValueError(f"{kind}: {e}") from None
    if style is not None and style not in styles:
        raise ValueError(f"{kind}: unknown style {style!r}; define it with an @style line")
    return sign


def build_cues(rows, cuts):
    cues = [Cue(t2f(a), min(t2f(b), TOTAL), wrap(text), raw=text) for a, b, text in rows]
    for c in cues:
        if c.start >= TOTAL:
            raise ValueError(f"subtitle starts at {f2t(c.start):.2f}s, after the video ends at {f2t(TOTAL):.2f}s: {c.raw!r}")
        if c.end <= c.start:
            raise ValueError(f"subtitle ends before it starts at {f2t(c.start):.2f}s: {c.raw!r}")
    min_f, max_f, linger = frames(MIN_SECONDS), frames(MAX_SECONDS), frames(LINGER_SECONDS)

    def need(c):
        return int(len(c.text.replace("\n", "")) / MAX_CPS * FPS) + 1

    def nearest_cut(frame, before, after):
        i = bisect.bisect_left(cuts, frame - frames(before))
        best = None
        while i < len(cuts) and cuts[i] <= frame + frames(after):
            if best is None or abs(cuts[i] - frame) < abs(best - frame):
                best = cuts[i]
            i += 1
        return best

    # Start exactly on a nearby camera cut: a subtitle appearing just off a cut is distracting.
    for c in cues:
        cut = nearest_cut(c.start, *SNAP_START)
        if cut is not None:
            c.start = cut

    # Give each subtitle time to be read, by holding it longer when the next one allows.
    for i, c in enumerate(cues):
        limit = (cues[i + 1].start - GAP_FRAMES) if i + 1 < len(cues) else TOTAL  # never past the last frame
        want = max(c.end + linger, c.start + min_f, c.start + need(c))
        c.end = min(max(c.end, min(want, limit)), c.start + max_f)

    # If one still reads too fast, start it a little early when there is room.
    for i, c in enumerate(cues):
        short = need(c) - (c.end - c.start)
        if short > 0:
            floor = (cues[i - 1].end + GAP_FRAMES) if i else 0
            c.start = max(floor, c.start - min(short, frames(EARLY_START)))

    # Tidy each end against the next subtitle and any cut.
    for i, c in enumerate(cues):
        nxt = cues[i + 1].start if i + 1 < len(cues) else None
        if nxt is not None:
            if nxt - c.end < frames(CLOSE_GAP_SECONDS):
                c.end = nxt - GAP_FRAMES
            c.end = min(c.end, nxt - GAP_FRAMES)
        cut = nearest_cut(c.end, *SNAP_END)
        if cut is not None and cut - GAP_FRAMES - c.start >= min_f and (nxt is None or cut <= nxt):
            if cut - GAP_FRAMES - c.start >= need(c) or cut - GAP_FRAMES > c.end:
                c.end = cut - GAP_FRAMES
        c.end = min(c.end, TOTAL)
    return cues


def check(cues):
    """Human-readable problems; an empty list means every subtitle passes."""
    problems = []
    min_f, max_f = frames(MIN_SECONDS), frames(MAX_SECONDS)
    for i, c in enumerate(cues):
        lines = c.text.split("\n")
        where = f"#{i + 1} {f2t(c.start):7.1f}s"
        if len(lines) > 2:
            problems.append(f"{where} more than two lines: {c.raw!r}")
        for line in lines:
            if len(line) > MAX_LINE:
                problems.append(f"{where} line too long ({len(line)} > {MAX_LINE}): {line!r}")
        if c.end - c.start < min_f:
            problems.append(f"{where} too short ({c.seconds:.2f}s): {c.raw!r}")
        if c.end - c.start > max_f:
            problems.append(f"{where} too long ({c.seconds:.1f}s): split it: {c.raw!r}")
        if c.cps > MAX_CPS + 0.5:
            problems.append(f"{where} too fast ({c.cps:.1f} cps over {c.seconds:.1f}s): shorten it: {c.raw!r}")
        if i + 1 < len(cues) and cues[i + 1].start - c.end < GAP_FRAMES:
            problems.append(f"{where} overlaps or touches the next subtitle: {c.raw!r}")
    return problems


def srt_time(frame):
    ms = int(round(f2t(frame) * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def write_srt(cues, path):
    out = [f"{i}\n{srt_time(c.start)} --> {srt_time(c.end)}\n{c.text}\n" for i, c in enumerate(cues, 1)]
    Path(path).write_text("\n".join(out), encoding="utf-8")
