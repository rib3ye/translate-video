"""Checks a burned video against its source: the same frame count and duration, audio bit-identical, each sampled
subtitle visible from exactly its first frame to its last, the picture unchanged where nothing was drawn, no decode
errors, and macOS can play the file. Prints PASS or FAIL per check; exits 1 if any fails.
Usage: verify.py <workdir> <burned.mp4> [--sample 120] [--seconds N] [--no-psnr]
--seconds N limits the checks to the first N seconds, for a test made with burn.py --seconds N."""
import argparse
import json
import random
import re
import statistics
import subprocess
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as cm
import subs_lib as sl

ap = argparse.ArgumentParser()
ap.add_argument("work")
ap.add_argument("burned")
ap.add_argument("--sample", type=int, default=120)
ap.add_argument("--seconds", type=float)
ap.add_argument("--no-psnr", action="store_true")
args = ap.parse_args()

work, burned = Path(args.work).resolve(), Path(args.burned).resolve()
meta = sl.setup(work)
source = meta["source"]
results = []


def report(name, ok, detail):
    results.append(ok)
    print(f"{'PASS' if ok else 'FAIL'}  {name}: {detail}", flush=True)


def probe(path, *a):
    return subprocess.run(["ffprobe", "-v", "error", *a, str(path)], capture_output=True, text=True, check=True).stdout


# 1. Frame count and duration
n_out = cm.count_frames(burned, "v:0")
duration = float(probe(burned, "-show_entries", "format=duration", "-of", "csv=p=0").strip())
if args.seconds:
    print(f"info  test file: {n_out} frames, {duration:.3f}s")
else:
    report("frames", n_out == meta["frames"], f"{n_out} burned, {meta['frames']} in the source")
    # Containers can disagree by a fraction of a second over edit lists; frames and audio bytes are the real test.
    report("duration", abs(duration - meta["duration"]) < 0.25, f"{duration:.6f}s burned, {meta['duration']:.6f}s source")

# 2. Audio: the copied packets must be byte for byte the source's
if not args.seconds:
    def md5(path, spec):
        cmd = ["ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error", "-i", str(path), "-map", spec, "-c", "copy",
               "-f", "md5", "-"]
        return subprocess.run(cmd, capture_output=True, text=True, check=True).stdout.strip()

    for k, a in enumerate(meta["audio"]):
        same = md5(source, f"0:{a['index']}") == md5(burned, f"0:a:{k}")
        report(f"audio stream {k}", same, "bit-identical to the source" if same else "differs from the source")

# 3. Subtitle timing: a patch inside the subtitle box must change exactly on each sampled subtitle's frames
cues = sl.build_cues(sl.load_rows(sorted((work / "translation").glob("part_*.tsv"))), sl.load_cuts(work / "survey/cuts.txt"))
limit = args.seconds or 1e9
cues = [c for c in cues if sl.f2t(c.end) + 1 < limit]
random.seed(7)
picked = random.sample(cues, min(args.sample, len(cues)))
want = {}
for c in picked:
    if c.start > 0:
        want[c.start - 1] = False
    want[c.start] = True
    want[c.end - 1] = True
    if c.end < meta["frames"]:  # a subtitle may run to the very last frame
        want[c.end] = False
frames = sorted(want)
geo = sl.geometry(meta)
k = geo["scale"]


def even(v):
    return max(2, int(v) // 2 * 2)  # 4:2:0 video crops at even sizes; an odd size gets rounded and misread


PW, PH = even(200 * k), even(34 * k)
PX, PY = even(meta["width"] / 2 - PW / 2), even(geo["bottom"] - 40 * k)


def grab(path, stream):
    cmd = ["ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error", "-i", str(path), "-map", f"0:{stream}", "-an",
           "-vf", f"crop={PW}:{PH}:{PX}:{PY},format=rgb24", "-fps_mode", "passthrough", "-f", "rawvideo", "-"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    size, wanted_set, last, out, n = PW * PH * 3, set(frames), frames[-1], [], 0
    while n <= last:
        buf = proc.stdout.read(size)
        if len(buf) < size:
            break
        if n in wanted_set:
            out.append(np.frombuffer(buf, dtype=np.uint8).reshape(PH, PW, 3).astype(np.int16))
        n += 1
    proc.kill()
    proc.wait()
    return np.stack(out) if out else np.zeros((0, PH, PW, 3), np.int16)


if frames:
    a, b = grab(source, meta["video_stream"]), grab(burned, "v:0")
    if len(a) != len(frames) or len(b) != len(frames):
        report("subtitle timing", False, f"could not read the frames: wanted {len(frames)}, got {len(a)} and {len(b)}")
    else:
        diff = np.abs(a - b).mean(axis=(1, 2, 3))
        on = [d for d, f in zip(diff, frames) if want[f]]
        off = [d for d, f in zip(diff, frames) if not want[f]]
        wrong = [(f, "should show" if want[f] else "should be clear", round(float(d), 1))
                 for d, f in zip(diff, frames) if (d > 6.0) != want[f]]
        detail = (f"{len(picked)} subtitles, {len(frames)} frames; difference from the source where one shows: "
                  f"min {min(on):.1f}; where none should: max {max(off) if off else 0:.1f}")
        report("subtitle timing", not wrong, detail + (f"; wrong frames: {wrong[:8]}" if wrong else ""))

# 4. Picture quality on frames with nothing drawn, and decode errors, in one pass
if not args.no_psnr:
    spans = json.loads((work / "overlay/spans.json").read_text())
    blank = np.zeros(meta["frames"] + 2, bool)
    for a0, b0, _, is_blank in spans:
        if is_blank:
            blank[a0:b0] = True
    cmd = ["ffmpeg", "-hide_banner", "-nostdin", "-v", "error", "-i", str(burned), "-i", source, "-lavfi",
           f"[0:v:0][1:{meta['video_stream']}]psnr=stats_file=psnr.log:shortest=1", "-f", "null", "-"]
    run = subprocess.run(cmd, cwd=work / "review", capture_output=True, text=True)
    values = []
    for line in (work / "review/psnr.log").read_text().splitlines():
        n = int(re.search(r"n:(\d+)", line).group(1)) - 1
        v = re.search(r"psnr_y:(\S+)", line).group(1)
        if n < len(blank) and blank[n]:
            values.append(99.0 if v == "inf" else float(v))
    if values:
        med = statistics.median(values)
        report("picture", med >= 42, f"PSNR-Y on {len(values)} frames with nothing drawn: median {med:.1f} dB, lowest "
               f"{min(values):.1f} dB, {sum(v < 40 for v in values)} frames under 40 dB")
    report("decoding", run.returncode == 0 and not run.stderr.strip(), run.stderr.strip()[:300] or "no errors")

# 5. macOS itself can play it
player = cm.BIN / "playable"
if player.exists():
    run = subprocess.run([str(player), str(burned)], capture_output=True, text=True)
    report("macOS playback", run.returncode == 0, run.stdout.strip())
sys.exit(0 if all(results) else 1)
