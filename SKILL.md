---
name: translate-video
description: Translate the speech and on-screen text of a foreign-language video (Japanese, Korean, Chinese, Spanish and more) into English and burn high-quality subtitles into the picture. Speech-to-text (Whisper, plus Kotoba-Whisper for Japanese), Apple OCR of the show's own captions, and an ffmpeg overlay burn that leaves the audio bit-identical all run on this Mac. The translating is Claude's own, checked by an independent reviewer, and runs on Anthropic's servers, which are sent the transcript text and the stills Claude opens but not the video or audio. Use this whenever someone wants a video translated, subtitled, captioned, hardsubbed or "burned in", asks for English subs on a show, clip or YouTube download, wants an SRT made from foreign speech, or wants an existing SRT burned into a video. That includes requests that mention DaVinci Resolve, Premiere, OpenRouter or a translation API, none of which this needs.
---

# Translate a video and burn in subtitles

The result is `<stem> - English subs.mp4` beside the original, with a dialogue-only `<stem> - English subs.srt`.
The picture is re-encoded once at visually lossless quality, every audio stream is copied bit for bit, and the
original file is never touched.

Per 30 minutes of 1080p video on a fast Apple-silicon Mac, expect about 15 minutes of preparation and 10 minutes of
encoding, both in the background, plus about an hour of your translating and a few minutes of checks.

Why it is built this way:
- This Mac's ffmpeg can't draw text: it has no libass, `subtitles` or `drawtext`. So each on-screen state is drawn
  as a transparent PNG with Pillow and laid over the video with ffmpeg's `overlay`, which also makes the timing
  frame-exact.
- Accuracy comes from three sources for every line: Whisper, a second speech model, and the show's own on-screen
  captions read by OCR. Japanese TV puts most of its dialogue on screen. An independent reviewer then checks every
  line.
- You do the translating. No API key, OpenRouter, or DaVinci Resolve is needed, even when the user offers one.
- Your translating and the reviewer's checking run on Anthropic's servers, not this Mac. They receive the sheets'
  text and every still either of you opens: for a 36-minute video, about 390,000 characters and 34 stills (11 MB).
  Speech-to-text, OCR, drawing and encoding run here, and the video file and its audio are processed only here.
  SendUserFile does upload the finished video for phone and web viewers, when it's under 500 MiB.

## Defaults

Go with these unless the user says otherwise. The source language is the only thing that might need asking, and
`--lang auto` detects it.
- English subtitles at the bottom centre, white Helvetica Neue on a dark box.
- They may overlap the show's own burned-in captions. Don't move them out of the way.
- On-screen text that carries meaning is translated too: topic cards, name tags and notes, drawn over or beside
  the original.
- Output goes next to the source video.

## Commands

Shell variables don't survive between Bash calls, so start each command with:
```bash
SKILL=~/.claude/skills/translate-video; PY=~/.cache/translate-video/venv/bin/python; WORK=<the work folder>
```
Run every script as `"$PY" -I -B "$SKILL/scripts/NAME.py" …`. The `-I` flag stops Python from loading stray
modules out of the current folder. The `-B` flag stops it writing `__pycache__` files into the skill, which would
record the user's home path.

Each video gets a work folder under `~/.cache/translate-video/work/`. `prepare.py` creates it and prints its path
as the last line. It sits outside the session scratchpad on purpose: a restart empties the scratchpad, and the
translation inside is hours of work.

## Steps

### 1. Check the machine (under a minute)
Run `bash "$SKILL/scripts/setup.sh" --check`. It lists the tools, the Python environment, the Swift tools and the
models, says which models each language needs, and downloads nothing. If anything needed is missing:
1. Run `python3 -I -B "$SKILL/scripts/get_models.py" --sizes --lang <code>`. It prints each model with its source
   and exact size.
2. Ask the user once about all the downloads. Name each file, its source and its size. The Python packages come
   from PyPI: under 1 GB to download, 1.3 GB installed. Downloading needs their yes.
3. Then run `bash "$SKILL/scripts/setup.sh"` and `"$PY" -I -B "$SKILL/scripts/get_models.py" --lang <code>`.

Japanese also gets Kotoba-Whisper (1.5 GB), which was trained on Japanese TV speech. The places where it disagrees
with Whisper are where mishearings hide. Other languages get Whisper alone unless the user accepts `--second`.
That adds 3.1 GB: the same Whisper with a different decoder, so it is a weaker cross-check.

### 2. Prepare (background; about 15 minutes per 30 minutes of video)
```bash
"$PY" -I -B "$SKILL/scripts/prepare.py" "/path/to/video.mp4" --lang ja
```
It probes the video, extracts the audio and two frames a second, finds camera cuts, reads on-screen text,
transcribes with both models, and writes the sheets you translate from. Those are `sheets/section_NN.txt`, three
minutes each, and a contact sheet `section_NN.jpg` for each. If it stops, run it again; finished steps are
skipped. Read any WARNING lines; references/pipeline-notes.md explains them. A NOTE about the audio's language tag
needs nothing from you, because burn.py corrects the tag.

### 3. Research while it runs
- Check memory for a glossary of this show, and use it if there is one.
- Otherwise find the official English title and the cast's English spellings. Netflix pages and English press come
  first; local fan sites help with nicknames. Note recurring terms.
- Write `$WORK/translation/glossary.md`: every name in the source script and in English, and every term with the
  rendering you chose. All sections use it, and it survives a context compaction. If memory has only the English
  names, add the source-script forms as they turn up in the sheets.
- Put the names and terms, in the source script, into `$WORK/asr/prompt.txt` for `relisten.py`.
- Some on-screen names may be in Latin letters inside a non-Latin show (KAI, SORA). The sheets drop Latin-only
  text, so rebuild them keeping those names: `prepare.py VIDEO --lang ja --keep-latin "KAI,SORA" --redo sheets`.

### 4. Translate one section at a time
Read references/translation.md first. It covers the sheet format, the part files, the reading-speed rules and the
craft. Then, for each section:
1. Read `sheets/section_NN.txt`. Open `section_NN.jpg` whenever it matters who is speaking. For a closer look,
   `frames/` has two frames a second; frame n shows about (n-1)/2 seconds.
2. Write `translation/part_NN.tsv`.
3. Run `check_subs.py $WORK` and fix every problem in that part.

Finish each file before you start the next. The files are your memory if the conversation gets compacted. Log
every line you're unsure of in `translation/doubts.tsv`, as start, end and why.

### 5. On-screen text
Read references/signs.md, then write `translation/signs.tsv`. Run `check_subs.py` again.

### 6. Independent review
A reviewer costs about 10 minutes and as many tokens as translating did. Under about 5 minutes of video, do this
pass yourself with the same brief instead.
1. Run `review_pack.py $WORK`. It writes `review/review_pack.txt`.
2. Spawn one general-purpose subagent with the review brief from references/translation.md, filled in for this
   video. It reads every line and reports problems; it edits nothing.
3. Check each reported problem against the sheets yourself, because reviewers are sometimes wrong.
4. Put the fixes you accept in a fix file, one per line as old text, a tab, then new text.
5. Run `apply_fixes.py $WORK FIXFILE`, then `check_subs.py`.

### 7. Render and look (a few minutes)
Run `render.py $WORK`, then `qa_sheet.py $WORK $WORK/review/qa.jpg T1 T2 …` with 6 to 10 moments. Include a
two-line subtitle, a two-speaker one, and each kind of sign. Open the image, then fix and re-render until it's
right.

### 8. Burn and verify
1. For a video over 10 minutes, run a test first: `burn.py $WORK $WORK/review/test.mp4 --seconds 300 --force`,
   then `verify.py $WORK $WORK/review/test.mp4 --seconds 300`. That catches a timing or colour problem in 2 minutes
   instead of after the full encode. Skip this for shorter videos, where the test would just repeat the real burn.
2. Run the full burn in the background: `burn.py $WORK "<dir>/<stem> - English subs.mp4"`. It takes about
   10 minutes per 30 minutes of 1080p. It also tags the audio with the spoken language when the source's tag is
   missing or wrong; YouTube downloads often say English.
3. Run `verify.py $WORK "<output>"` (about 2 minutes). Every line must say PASS. references/pipeline-notes.md
   explains each check.

### 9. Deliver
1. Copy `$WORK/translation/subs.srt` to `<dir>/<stem> - English subs.srt`.
2. Look at 4 to 6 frames of the final file:
   `qa_sheet.py $WORK $WORK/review/final.jpg T1 … --video "<output>"`.
3. Report to the user in this order:
   1. A link to the video.
   2. What got translated.
   3. The check results, as numbers.
   4. The least-certain spots from doubts.tsv, each as mm:ss with a plain description.
   5. Anything you left out on purpose.
4. Save the show's glossary to memory, or update it. Include each name in the source script and in English, the
   terms, who is who, and traps such as two similar names.
5. Delete the bulky leftovers: `frames/`, `overlay/`, `audio/`, `review/test.mp4`, `review/psnr.log` and
   `survey/frame_*.png`. The first three come to about 700 MB per 30 minutes; all of it can be regenerated. Keep
   everything else for later fixes.

## Later fixes
Edit the part file, or use `apply_fixes.py`. Then run `render.py`, `burn.py --force` and `verify.py`. None of them
needs the frames or the audio.

## Burning subtitles that already exist
```bash
"$PY" -I -B "$SKILL/scripts/prepare.py" VIDEO --lang <spoken language code> --only probe,cuts
"$PY" -I -B "$SKILL/scripts/import_srt.py" SUBS.srt WORK
```
Run `check_subs.py` (imported files often read too fast), then steps 7 to 9.

## When something looks wrong
If a script warns or fails, or a check or result looks off, read references/pipeline-notes.md. It lists every
failure met so far and what fixed it.
