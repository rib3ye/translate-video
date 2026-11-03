# Translating from the sheets

1. Reading a section sheet
2. Writing part files
3. The rules check_subs.py enforces
4. Craft
5. Doubtful lines
6. The review brief

## 1. Reading a section sheet

Each row is a label, a time range in seconds from the start of the video, and text.

| Label | Source | How far to trust it |
|---|---|---|
| `W` | Whisper large-v3 | Best timing. `[413.9]` marks a pause at 413.9 s, a natural place to split. `?` means Whisper itself was unsure; those rows are often hallucinations over music or crosstalk, but they are sometimes right. |
| `S` | second transcript (Kotoba-Whisper for Japanese) | Independent ears. Its timestamps can drift a few seconds. |
| `T` | captions burned in at the bottom of the screen, read by OCR | The strongest evidence for wording, since the show's editors wrote them. But they paraphrase, shorten and add jokes, and OCR garbles some characters. |
| `C`, `L`, `O` | other on-screen text: top right, top left, elsewhere | Topic cards, name tags, logos and props. These are the candidates for signs.tsv. |

`@(x,y)` is the top-left corner of the text as fractions of the frame.

A made-up example of the format:
```
C 410.0-452.5 @(0.62,0.05)  初対面の印象は？
W 412.0-418.4  正直、最初はちょっと怖かったんですけど、[415.6]話してみたらすごい優しくて
S 411.7-418.9  正直最初はちょっと怖かったんですけど話してみたらすごい優しくて
T 412.5-418.5 @(0.18,0.84)  最初はちょっと怖かったけど 話したら優しかった
```

When the sources disagree:
- **Names:** use the glossary, then T. Speech models often write a name with the wrong characters or as an ordinary
  word: Whisper may write 斉藤 for a guest spelled 斎藤, or 春 (spring) for a nickname written ハル.
- **Wording:** use T when it matches the sense of the speech. Otherwise use the reading that W and S share.
- **One model only:** if just one model hears something and it is nonsense, ignore it.

Known hallucinations appear during music and silence: repeated phrases, and for Japanese ご視聴ありがとうございました
("thanks for watching").

Contact sheets show 36 frames per section (one every 5 seconds in a full section), labelled in seconds. Use them to
see who is on screen, who is wearing what, and whether a clip from an older episode is playing. For quick
exchanges and split screens, open `frames/NNNNN.jpg` directly. There are two a second, and frame n shows about
(n-1)/2 seconds, give or take a quarter second. `inspect_frame.py` shows an exact moment.

## 2. Writing part files

Write `translation/part_NN.tsv` for section NN, one row per subtitle: `start<TAB>end<TAB>text`.
- Times are when the speech starts and stops, taken from W and its pause marks. The scripts add reading time, snap
  starts to camera cuts and keep the gaps, so don't pad by hand.
- `|` forces a line break. Without one, lines wrap at the most natural point.
- Two speakers in one subtitle are written `-Love him!|-Me, too!`, one speaker per line.
- Lines starting with `#` are comments. Start each file with one saying what the section covers, so a later reader,
  possibly you after a compaction, can find their place.

The made-up example above becomes:
```
# 06:50 to 07:00  first impressions of the new arrivals
412.0	415.5	Honestly, at first I was a little scared of him,
415.6	418.4	but once we talked, he was so kind.
```

## 3. The rules check_subs.py enforces

These follow Netflix's English subtitle standard:
- At most 42 characters per line (32 for portrait video), and at most 2 lines.
- At most 20 characters per second.
- On screen for at least 5/6 of a second and at most 7 seconds.
- A gap of at least 2 frames between subtitles. Gaps under half a second are closed to 2 frames, which reads
  better than a flicker.

When a subtitle reads too fast, cut words; don't stretch it past the speech. When speech runs over 7 seconds, split
it at a pause mark.

## 4. Craft

- **Meaning first.** Write the English a native speaker would actually say, in the speaker's register. Rough talk
  stays rough, teasing stays playful, and polite stays polite. Don't soften swearing and don't add any.
- **Condense.** Drop fillers, false starts and repetition. Keep names, the joke and the point. Reading speed decides
  how much fits.
- **One thought per subtitle.** Split at pause marks and sentence ends. A subtitle shouldn't run across a camera
  cut or a change of speaker, except in the two-speaker form.
- **Who.** He, she, I and you must match who is speaking and who they mean. Check the contact sheet, name tags and
  context. After a wrong meaning, a wrong person is the worst error. The first run's review caught one cast member
  written where another with a similar name was meant.
- **Names and terms.** Use the show's official English spellings from the glossary. Keep -san, -kun and -chan for
  Japanese, as the first run did: they carry relationships English lacks. A term with no good English, such as
  senpai or kotatsu, stays as it is. Decide once and log it in the glossary.
- **Songs.** Don't transcribe or translate lyrics. A ♪ subtitle at most.
- **Children and childhood stories** (school crushes, first loves) stay strictly innocent. If a garbled line could
  be read otherwise, leave it out.
- **Leave out** laughter, filler-only crosstalk, and stretches nobody can make out. An empty screen beats an
  invented line.

## 5. Doubtful lines

- **Listen again with context.** With names and vocabulary in `asr/prompt.txt`, run
  `relisten.py $WORK 185-192 47-53`. It prints a prompted reading (P) and a plain one (N) for each range.
  - Trust P only where N or a caption agrees. Over unclear audio, the prompted model echoes the prompt's own words.
    In the trial run, 一家団欒 came back four times.
  - Keep ranges at least 5 seconds long. Windows of 2 to 3 seconds produce hallucinations such as お疲れ様でした,
    or one word repeated dozens of times.
- **Still unsure, but it matters:** give your best guess and log it in `translation/doubts.tsv` as start, end and
  why. Those rows become the "least certain" list in the final report.
- **Unsure and it doesn't matter:** leave it out.

## 6. The review brief

Fill in the angle brackets and pass the result as the subagent's prompt.

```
You are reviewing English subtitles for a <length> <language> <kind of video>, checking them against the
<language>. You have no audio. Do not edit any files; report back only.

Read this file in full (it is long, read it in chunks): <WORK>/review/review_pack.txt

Each row is time-ordered, with times in seconds:
- `E#n start-end (cps) text` is the English subtitle under review. " / " is a line break.
- `W` is Whisper speech-to-text. Noisy, with good timing.
- `S` is a second speech-to-text model. Noisy, and its timestamps can drift several seconds.
- `T` is on-screen text read by OCR, written by the show's editors. It is the most trustworthy for wording, but it
  sometimes paraphrases or shortens the speech, and OCR can garble it. T rows also include stray misreads of props.
- `RP` and `RN` (if any) are targeted re-listens of doubtful stretches: RP with the show's names as a prompt, RN
  without. RP can echo the prompt's words over unclear audio, so trust it only where another row agrees.

To see who is on screen, use <WORK>/sheets/section_NN.jpg (labelled in seconds). For a closer look,
<WORK>/frames/NNNNN.jpg has two frames a second, where frame n shows about (n-1)/2 seconds. Use them only where
the speaker genuinely matters.

Context: <the show and its premise; the glossary: every name in the source script with its English spelling, and
each term with its chosen rendering>

What to look for, in order of importance:
1. Wrong meaning: the English says something the source doesn't, or misses the point of a line or joke.
2. Wrong person: a he/she/you/I that misassigns who did what, judged from the source and context.
3. Spoken lines that matter but have no subtitle. Ignore filler, laughter, and stretches where W and S clearly
   hallucinated.
4. English that reads unnaturally, or a tone badly off for the speaker. Skip mere style preferences; the current
   wording is fine unless a native speaker would stumble.

Where W, S and T disagree, say what you think was actually said and how sure you are. Lines about childhood stay
strictly innocent. Never add song lyrics.

Constraints for any replacement text: at most 2 lines, at most 42 characters per line, and no more than 20
characters per second for that subtitle's duration. Use "|" for a forced line break. Two speakers in one subtitle
are written `-Line one|-Line two`.

Report back only real problems, most serious first, one per line, in exactly this form, with no preamble and no
praise:
`E#n | high/medium/low | current English | proposed English | why, citing the source`
For a missing line use `AFTER E#n | ... | (missing) | proposed English | start-end seconds and the source text`.
Then give one final line stating how many subtitles you actually read. If a stretch was too garbled to judge, list
its time range rather than guessing.
```

A missing line comes back as a new row for the part file, not a fix-file entry: add it by hand.
