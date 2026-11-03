"""Shows or downloads the speech-to-text models, into ~/.cache/translate-video/models.
  python3 -I -B get_models.py --sizes --lang ja     list each file, its source and exact size; downloads nothing
  "$PY" -I -B get_models.py --lang ja [--second]    download what that language needs; --second adds the optional
                                                     second opinion for a language other than Japanese
Ask the user before downloading: name each file, where it comes from, and its size."""
import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as cm

ap = argparse.ArgumentParser()
ap.add_argument("--lang", required=True, help="Whisper language code of the source, e.g. ja")
ap.add_argument("--sizes", action="store_true")
ap.add_argument("--second", action="store_true")
args = ap.parse_args()

needed = [cm.MAIN_MODEL]
optional = []
if args.lang in cm.SECOND_MODEL:
    needed.append(cm.SECOND_MODEL[args.lang])
elif args.second:
    needed.append(cm.SECOND_FALLBACK)
else:
    optional.append(cm.SECOND_FALLBACK)

if args.sizes:
    total = 0
    for name in needed + optional:
        repo, files = cm.MODEL_FILES[name]
        listing = subprocess.run(
            ["curl", "-sfL", f"https://huggingface.co/api/models/{repo}/tree/main"], capture_output=True, text=True
        )
        if listing.returncode:
            raise SystemExit(f"could not list huggingface.co/{repo}; check the repo still exists")
        sizes = {x["path"]: x.get("size", 0) for x in json.loads(listing.stdout)}
        gone = [f for f in files if f not in sizes]
        if gone:
            raise SystemExit(f"huggingface.co/{repo} no longer has {gone}; check the repo before downloading")
        size = sum(sizes[f] for f in files)
        have = all((cm.MODELS / name / f).exists() for f in files)
        big = max(files, key=lambda f: sizes[f])
        state = "already downloaded" if have else ("optional" if name in optional else "needed")
        if state == "needed":
            total += size
        print(f"{name}: {state}, {size / 1e9:.2f} GB from huggingface.co/{repo} (mostly {big})")
    print(f"total needed: {total / 1e9:.2f} GB")
else:
    from huggingface_hub import snapshot_download

    for name in needed:
        repo, files = cm.MODEL_FILES[name]
        snapshot_download(repo, local_dir=str(cm.MODELS / name), allow_patterns=files)
        print(f"{name}: ok in {cm.MODELS / name}")
