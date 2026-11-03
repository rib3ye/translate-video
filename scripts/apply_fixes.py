"""Replaces whole subtitle texts in the part files. The fix file has one fix per line: the old text, a tab, the new
text, both exactly as written in the part files ("|" breaks included). Changes nothing unless every old text
matches exactly one subtitle. Usage: apply_fixes.py <workdir> <fixfile>"""
import sys
from pathlib import Path

translation, fixfile = Path(sys.argv[1]).resolve() / "translation", Path(sys.argv[2])
files = {p: p.read_text(encoding="utf-8").split("\n") for p in sorted(translation.glob("part_*.tsv"))}
count = 0
for raw in fixfile.read_text(encoding="utf-8").splitlines():
    if not raw.strip() or raw.startswith("#"):
        continue
    if raw.count("\t") != 1:
        raise SystemExit(f"each fix needs exactly one tab, between old and new text: {raw!r}")
    old, new = raw.split("\t")
    if not new.strip():
        raise SystemExit(f"empty replacement for {old!r}; delete the row by hand instead")
    hits = [(p, i) for p, lines in files.items() for i, line in enumerate(lines)
            if len(line.split("\t")) == 3 and line.split("\t")[2] == old]
    if len(hits) != 1:
        raise SystemExit(f"expected one subtitle reading {old!r}, found {len(hits)}; nothing changed")
    p, i = hits[0]
    parts = files[p][i].split("\t")
    parts[2] = new
    files[p][i] = "\t".join(parts)
    count += 1
for p, lines in files.items():
    p.write_text("\n".join(lines), encoding="utf-8")
print(count, "fixes applied")
