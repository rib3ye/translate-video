"""Turns frame-by-frame OCR into on-screen text "tracks": one row per piece of text, with its time range, position and
screen region. prepare.py runs it. Usage: ocr_tracks.py <ocr.jsonl> <tracks.json>"""
import json
import sys
from collections import Counter
from difflib import SequenceMatcher

STEP = 0.5  # seconds between OCR frames


def similar(a, b):
    return 1.0 if a == b else SequenceMatcher(None, a, b).ratio()


def extends(old, new):
    """True when new is old with more text after it: a caption revealed in steps, often for a punchline."""
    core = old.rstrip("・.…。、!?！？ ")
    return len(new) >= len(old) + 2 and len(core) >= 2 and similar(core, new[: len(core)]) >= 0.8


def region(cx, cy):
    if cy >= 0.72:
        return "bottom"
    if cy <= 0.14 and cx >= 0.55:
        return "topright"
    if cy <= 0.22 and cx <= 0.25:
        return "topleft"
    return "other"


def build(ocr_path, out_path):
    tracks, active = [], []
    for line in open(ocr_path, encoding="utf-8"):
        frame = json.loads(line)
        t = (int(frame["file"].split(".")[0]) - 1) * STEP
        next_active = []
        for b in frame["boxes"]:
            text = b["text"].strip()
            if not text or b["conf"] < 0.3:
                continue
            cx, cy = b["x"] + b["w"] / 2, b["y"] + b["h"] / 2
            best, best_score = None, 0.0
            for tr in active:
                if abs(tr["cx"] - cx) > 0.12 or abs(tr["cy"] - cy) > 0.05:
                    continue
                score = similar(tr["texts"].most_common(1)[0][0], text)
                if score > best_score:
                    best, best_score = tr, score
            if best is not None and best_score >= 0.55 and not extends(best["texts"].most_common(1)[0][0], text):
                tr = best
                tr["texts"][text] += 1
                tr["end"], tr["last"] = t + STEP, t
                tr["cx"], tr["cy"] = cx, cy
                tr["conf"] = max(tr["conf"], b["conf"])
                tr["w"], tr["h"] = max(tr["w"], b["w"]), max(tr["h"], b["h"])
            else:
                tr = {"start": t, "end": t + STEP, "last": t, "cx": cx, "cy": cy, "x": b["x"], "y": b["y"],
                      "w": b["w"], "h": b["h"], "conf": b["conf"], "texts": Counter({text: 1})}
                tracks.append(tr)
            if tr not in next_active:
                next_active.append(tr)
        # keep a track alive across one or two missed reads
        active = next_active + [tr for tr in active if tr not in next_active and t - tr["last"] <= 1.0]

    rows = []
    for tr in tracks:
        if tr["end"] - tr["start"] < 1.0 and tr["conf"] < 0.5:
            continue
        rows.append({
            "start": tr["start"], "end": tr["end"], "text": tr["texts"].most_common(1)[0][0],
            "region": region(tr["cx"], tr["cy"]), "x": round(tr["x"], 3), "y": round(tr["y"], 3),
            "w": round(tr["w"], 3), "h": round(tr["h"], 3), "conf": round(tr["conf"], 2),
        })
    rows.sort(key=lambda r: r["start"])
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(rows, fh, ensure_ascii=False, indent=0)
    print(len(rows), "on-screen text tracks", dict(Counter(r["region"] for r in rows)))
    return rows


def for_sheets(tracks, duration):
    """Returns (track, note) pairs for the sheets. A logo or watermark that stays in one place gets misread a dozen
    ways, and each misreading would start a new row. For such a place, keep the first read and note how many similar
    rereads were left out. Bottom captions are never collapsed: they sit in one place too, but each one is new
    dialogue."""
    places = []
    for t in sorted(tracks, key=lambda r: r["start"]):
        cx, cy = t["x"] + t["w"] / 2, t["y"] + t["h"] / 2
        place = next((p for p in places if abs(p["cx"] - cx) <= 0.06 and abs(p["cy"] - cy) <= 0.04), None)
        if place is None:
            place = {"cx": cx, "cy": cy, "tracks": []}
            places.append(place)
        place["tracks"].append(t)
    out = []
    for p in places:
        group = p["tracks"]
        if region(p["cx"], p["cy"]) != "bottom" and sum(t["end"] - t["start"] for t in group) > 0.3 * duration:
            totals = Counter()
            for t in group:
                totals[t["text"]] += t["end"] - t["start"]
            main = totals.most_common(1)[0][0]
            # rereads: text like the main one, or read with low confidence (misreads of a logo are unsure)
            same = [t for t in group if similar(t["text"], main) >= 0.3 or t["conf"] < 0.8]
            if len(same) > 2:
                until = max(t["end"] for t in same)
                out.append((same[0], f"(stays on screen until {until:.1f}s: {len(same) - 1} similar rereads left out)"))
                out.extend((t, "") for t in group if t not in same)
                continue
        out.extend((t, "") for t in group)
    return sorted(out, key=lambda r: r[0]["start"])


if __name__ == "__main__":
    build(*sys.argv[1:3])
