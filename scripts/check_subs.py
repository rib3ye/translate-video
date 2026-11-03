"""Quick check while translating: builds the subtitles from the part files with the real timing rules, lists every
subtitle that breaks one, and checks that signs.tsv parses. Exits 1 when anything needs fixing.
Usage: check_subs.py <workdir>"""
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import subs_lib as sl

work = Path(sys.argv[1]).resolve()
meta = sl.setup(work)
parts = sorted((work / "translation").glob("part_*.tsv"))
if not parts:
    raise SystemExit("no translation/part_*.tsv yet")
try:
    rows = sl.load_rows(parts)
    cues = sl.build_cues(rows, sl.load_cuts(work / "survey/cuts.txt"))
except ValueError as e:
    raise SystemExit(str(e))
problems = sl.check(cues)

sign_rows, defined = sl.load_signs(work / "translation/signs.tsv")
try:
    styles = sl.styles_from(defined)
except ValueError as e:
    styles = sl.styles_from({})
    problems.append(f"signs.tsv style: {e}")
for a, b, kind, text, lineno in sign_rows:
    try:
        sl.parse_kind(kind, styles)
    except ValueError as e:
        problems.append(f"signs.tsv:{lineno}: {e}")
    if b <= a:
        problems.append(f"signs.tsv:{lineno}: ends before it starts")

cps = [c.cps for c in cues]
print(f"{len(cues)} subtitles from {len(parts)} part files; the last ends at {sl.f2t(cues[-1].end):.1f}s of "
      f"{meta['duration']:.1f}s; reading speed median {statistics.median(cps):.1f}, max {max(cps):.1f} characters/s; "
      f"{len(sign_rows)} signs")
print(f"{len(problems)} problems" + (":" if problems else ""))
for p in problems:
    print("  ", p)
sys.exit(1 if problems else 0)
