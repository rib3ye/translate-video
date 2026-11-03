"""Burns the rendered overlays into the video. The picture is re-encoded once (x264, CRF 16, visually lossless), every
audio stream is copied untouched, and the frame count stays exactly the source's.
Usage: burn.py <workdir> <out.mp4> [--audio-lang auto|keep|jpn] [--crf 16] [--preset slow] [--seconds N] [--force]
--seconds N encodes just the first N seconds, faster, as a test to check with verify.py --seconds N.
--audio-lang: by default the transcribed audio stream is tagged with the spoken language when its tag is missing or
wrong (YouTube downloads often say "eng" for any language); "keep" leaves the tags, a code such as kor sets one."""
import argparse
import shlex
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as cm

MP4_AUDIO = {"aac", "mp3", "ac3", "eac3", "alac", "opus", "flac", "mp2"}

ap = argparse.ArgumentParser()
ap.add_argument("work")
ap.add_argument("out")
ap.add_argument("--audio-lang", default="auto")
ap.add_argument("--crf", type=float, default=16)
ap.add_argument("--preset", default="slow")
ap.add_argument("--seconds", type=float)
ap.add_argument("--force", action="store_true", help="replace the output file if it exists")
args = ap.parse_args()

work, out = Path(args.work).resolve(), Path(args.out).expanduser().resolve()
meta = cm.load_meta(work)
listing = work / "overlay" / "list.ffconcat"
if not listing.exists():
    raise SystemExit("run render.py first")
if meta["color"].get("color_transfer") in ("smpte2084", "arib-std-b67"):
    raise SystemExit("HDR source: tone-map it to SDR first; these overlay colours and encode settings are SDR only")
mp4 = out.suffix.lower() in (".mp4", ".m4v", ".mov")
if mp4 and any(a["codec"] not in MP4_AUDIO for a in meta["audio"]):
    raise SystemExit(f"MP4 can't hold this audio as-is ({[a['codec'] for a in meta['audio']]}): name the output .mkv")
if out == Path(meta["source"]):
    raise SystemExit("refusing to write over the source video")

# Overlays are RGB; convert them to the video's own YCbCr matrix and TV range, so colours match what players show.
matrix = meta.get("matrix", "bt709")
shift = f"setpts=PTS+{meta['video_offset']:.6f}/TB," if meta.get("video_offset", 0) > 0.0005 else ""
sub = f"[1:v]{shift}format=rgba,scale=in_range=pc:out_range=tv:out_color_matrix={matrix},format=yuva420p[sub]"
# trim, not -frames:v: the overlay list's last entry yields one surplus frame, and -frames:v would also cut the
# audio's tail off.
graph = f"{sub};[0:{meta['video_stream']}][sub]overlay=format=yuv420:eof_action=repeat,trim=end_frame={meta['frames']}[v]"

k = meta.get("audio_stream", 0)
lang_tag = cm.audio_tag_fix(meta) if args.audio_lang == "auto" else (None if args.audio_lang == "keep" else args.audio_lang)
if lang_tag:
    print(f"tagging audio stream {k} as {lang_tag} (the source says {meta['audio'][k].get('language') or 'nothing'})")

defaults = {"bt709": ("bt709", "bt709", "bt709"), "bt601": ("smpte170m", "smpte170m", "smpte170m")}[matrix]


def tag(key, default):
    value = meta["color"].get(key)
    return value if value and value not in ("unknown", "reserved", "unspecified") else default


level = []
if meta["width"] * meta["height"] <= 1920 * 1088:
    level = ["-level:v", "4.1" if meta["fps"] <= 30.5 else "4.2"]  # plays on older TVs and phones
cmd = [
    "ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "warning", "-nostats", "-y" if args.force else "-n",
    "-i", meta["source"], "-f", "concat", "-safe", "0", "-i", str(listing),
    "-filter_complex", graph, "-map", "[v]", "-map", "0:a?", "-map_metadata", "0",
    *([f"-metadata:s:a:{k}", f"language={lang_tag}"] if lang_tag else []),
    "-c:v", "libx264", "-preset", "veryfast" if args.seconds else args.preset, "-crf", f"{args.crf:g}",
    "-profile:v", "high", *level, "-pix_fmt", "yuv420p",
    "-colorspace", tag("color_space", defaults[0]), "-color_primaries", tag("color_primaries", defaults[1]),
    "-color_trc", tag("color_transfer", defaults[2]), "-color_range", "tv",
    "-fps_mode", "passthrough", "-c:a", "copy",
    *(["-t", f"{args.seconds:g}"] if args.seconds else []),
    *(["-movflags", "+faststart"] if mp4 else []),
    str(out),
]
print(shlex.join(cmd), flush=True)
t0 = time.time()
subprocess.run(cmd, check=True)
took = time.time() - t0
count = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_packets", "-show_entries",
                        "stream=nb_read_packets", "-of", "csv=p=0", str(out)], capture_output=True, text=True).stdout
frames = int(count.strip().split(",")[0] or 0)
print(f"wrote {out} ({out.stat().st_size / 1e9:.2f} GB, {frames} frames) in {took / 60:.1f} min, {frames / took:.0f} fps")
