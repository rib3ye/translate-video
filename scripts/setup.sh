#!/bin/bash
# Sets up this Mac for the translate-video scripts, in ~/.cache/translate-video: a Python environment and two small
# Swift tools (Apple OCR, and a "can macOS play this file" check). Safe to re-run: it skips what is already there.
#   setup.sh --check   report what is present or missing; changes nothing, downloads nothing
#   setup.sh           install what is missing; downloads Python packages from PyPI through uv (under 1 GB)
# The speech models are separate: see get_models.py.
set -uo pipefail
HOME_DIR="${TRANSLATE_VIDEO_HOME:-$HOME/.cache/translate-video}"
SKILL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PY="$HOME_DIR/venv/bin/python"
CHECK=0
[ "${1:-}" = "--check" ] && CHECK=1
missing=0
say() { printf '%-14s %s\n' "$1" "$2"; }

for t in ffmpeg ffprobe uv swiftc; do
  if command -v "$t" >/dev/null; then say "$t" "ok"; else say "$t" "MISSING"; missing=1; fi
done
if command -v ffmpeg >/dev/null; then
  say "ffmpeg" "version $(ffmpeg -hide_banner -version | head -1 | awk '{print $3}')"
  ffmpeg -hide_banner -encoders 2>/dev/null | grep -q libx264 || { say "libx264" "MISSING from this ffmpeg"; missing=1; }
fi
[ "$(uname -m)" = arm64 ] || { say "Apple Silicon" "NO: mlx-whisper needs an M-series Mac"; missing=1; }

if [ -x "$PY" ] && "$PY" -I -c "import mlx_whisper, faster_whisper, PIL, numpy, huggingface_hub" 2>/dev/null; then
  say "python env" "ok ($HOME_DIR/venv)"
elif [ $CHECK = 1 ]; then
  say "python env" "MISSING (setup.sh installs mlx-whisper, faster-whisper, pillow, numpy, huggingface_hub)"
  missing=1
else
  mkdir -p "$HOME_DIR"
  [ -x "$PY" ] || uv venv --quiet --python 3.12 "$HOME_DIR/venv" || exit 1
  uv pip install --quiet --python "$PY" mlx-whisper faster-whisper pillow numpy huggingface_hub || exit 1
  "$PY" -I -c "import mlx_whisper, faster_whisper, PIL" && say "python env" "installed ($HOME_DIR/venv)"
fi

for tool in ocr playable; do
  src="$SKILL_DIR/scripts/$tool.swift"
  bin="$HOME_DIR/bin/$tool"
  if [ -x "$bin" ] && [ "$bin" -nt "$src" ]; then
    say "$tool tool" "ok"
  elif [ $CHECK = 1 ]; then
    say "$tool tool" "MISSING (setup.sh compiles it; no download)"
    missing=1
  else
    mkdir -p "$HOME_DIR/bin"
    swiftc -O -swift-version 5 -suppress-warnings "$src" -o "$bin" || exit 1
    say "$tool tool" "compiled"
  fi
done

for m in whisper-large-v3-mlx kotoba-v2.0-faster faster-whisper-large-v3; do
  case $m in
    whisper-large-v3-mlx) use="needed for every language" ;;
    kotoba-v2.0-faster) use="needed for Japanese only" ;;
    *) use="optional: get_models.py --second, for other languages" ;;
  esac
  if compgen -G "$HOME_DIR/models/$m/*.npz" >/dev/null || compgen -G "$HOME_DIR/models/$m/*.bin" >/dev/null; then
    say "model" "$m: ok ($use)"
  else
    say "model" "$m: not downloaded ($use)"
  fi
done
exit $missing
