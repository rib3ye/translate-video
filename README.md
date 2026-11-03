# translate-video

A [Claude Code](https://claude.com/claude-code) skill that translates the speech and on-screen text of a
foreign-language video into English and burns the subtitles into the picture.

Every line is checked against three sources:
- two speech-to-text models
- the show's own burned-in captions, read with Apple's OCR

Claude translates from those sources, and a second Claude agent reviews every line. The subtitles and the
translated on-screen cards are drawn as images and laid over the video with ffmpeg. The picture is re-encoded once
at visually lossless quality, and the audio is copied bit for bit.

It was built on Japanese TV, which puts most of its dialogue on screen, but it handles other languages too.

## What runs where

- **On your Mac:** speech-to-text (Whisper large-v3, plus Kotoba-Whisper for Japanese), OCR, drawing and encoding.
  The video file and its audio are processed only here.
- **On Anthropic's servers:** the translating and the review, because Claude does them. Claude sees the transcript
  text and the still frames it opens. For a 36-minute video that came to about 390,000 characters and 34 stills.

## Requirements

- **Mac:** one with Apple silicon, because mlx-whisper needs it.
- **Tools:** ffmpeg with libx264, uv, and the Xcode command-line tools (for `swiftc`). For example, run
  `brew install ffmpeg uv` and `xcode-select --install`.
- **Claude Code.**
- **Disk space for the speech models.** The first run lists each model with its size and asks before downloading.

## Install

```bash
git clone https://github.com/rib3ye/translate-video ~/.claude/skills/translate-video
```

Then ask Claude Code to translate a video, or type `/translate-video /path/to/video.mp4`. The first run checks the
machine and asks before downloading anything. Everything it installs goes in `~/.cache/translate-video`.

Per 30 minutes of 1080p video, expect about 15 minutes of preparation and 10 minutes of encoding on a fast
Apple-silicon Mac, plus the time Claude spends translating.

## License

MIT
