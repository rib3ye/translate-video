"""Turns an existing SRT into translation/part_00.tsv, to burn subtitles someone already has. Formatting tags are
dropped; line breaks become "|". The timing is then fitted to the same rules as a fresh translation.
Usage: import_srt.py <file.srt> <workdir> [--force]"""
import re
import sys
from pathlib import Path

srt, work = Path(sys.argv[1]), Path(sys.argv[2]).resolve()
out = work / "translation" / "part_00.tsv"
if out.exists() and "--force" not in sys.argv:
    raise SystemExit(f"{out} already exists; pass --force to replace it")


def seconds(stamp):
    h, m, s = stamp.replace(",", ".").split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


rows = []
for block in re.split(r"\n\s*\n", srt.read_text(encoding="utf-8-sig").replace("\r", "")):
    lines = block.strip().split("\n")
    for i, line in enumerate(lines):
        m = re.match(r"\s*(\d+:\d+:\d+[,.]\d+)\s*-->\s*(\d+:\d+:\d+[,.]\d+)", line)
        if m:
            text = "|".join(re.sub(r"<[^>]+>|\{[^}]*\}", "", t).strip() for t in lines[i + 1 :] if t.strip())
            if text:
                rows.append(f"{seconds(m.group(1)):.3f}\t{seconds(m.group(2)):.3f}\t{text}")
            break
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(f"# imported from {srt.name}\n" + "\n".join(rows) + "\n", encoding="utf-8")
print(len(rows), "subtitles ->", out)
