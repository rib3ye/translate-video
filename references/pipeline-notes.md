# Pipeline notes: why each step is the way it is

Read this when a script warns, fails, or a result looks off.

## prepare.py warnings

- **Variable frame rate.** Subtitle timing counts frames at one constant rate. Convert first, then prepare the
  converted file:
  `ffmpeg -i IN -fps_mode cfr -r <fps_fraction from meta.json> -c:a copy OUT`.
- **HDR (PQ or HLG).** The overlay colours and encode settings are SDR only, so burn.py refuses. Tone-map to SDR
  first.
- **Audio starts N seconds from the video.** `audio/mono16k.wav` is padded or trimmed so that its second 0 is the
  first video frame, which keeps transcript times on the video's clock. Nothing else to do.

## meta.json settings you may edit

Edit these after prepare.py has created the file. A later `--redo probe` would reset them.
- `sub_size`: the subtitle font size in pixels. The default is 48 at 1080p.
- `sub_bottom`: the bottom edge of the subtitle box in pixels.
- `box_alpha`: the box opacity, 0 to 255. The default is 190.
- `max_line`: the maximum characters per line, 42 by default and 32 for portrait video.
- `max_cps`: the reading-speed limit. 20 is the Netflix adult standard; 17 suits children's content.

## How the burn works

The filter chain in burn.py, piece by piece:
- **The overlay list.** `overlay/list.ffconcat` is an ffmpeg concat list of full-frame PNGs, each with a duration.
  Each change is timed half a frame before its frame, so rounding can never make a subtitle a frame late.
- **`option framerate 1000000`** after each file in the list gives every PNG a microsecond clock. Without it, each
  PNG gets a 1/25 s clock, and every change rounds to a 40 ms step. At 23.976 fps that still lands inside half a
  frame, with 0.85 ms to spare. At 29.97 fps and above, testing put every subtitle one frame early.
- **The start offset.** When the video starts later than the audio (often one or two frames after an x264
  re-encode), `setpts=PTS+offset/TB` shifts the overlays to match. meta.json records it as `video_offset`.
- **Colour conversion.** Each PNG is RGB, so it is converted with
  `scale=in_range=pc:out_range=tv:out_color_matrix=<bt709 or bt601>` before `overlay=format=yuv420`. Without that,
  ffmpeg would use the BT.601 matrix on HD video, and coloured plates would come out a shade off from what
  players show.
- **eof_action=repeat** holds the last overlay until the video ends.
- **trim=end_frame=N** keeps exactly the source's frame count. The list's final entry produces one surplus frame.
  The first run removed it with `-frames:v`, but on an output that also copies audio, that cut about 65 ms off the
  end of the audio. Trimming inside the filter graph doesn't touch the audio.
- **The encode.** x264, `-preset slow -crf 16`, High profile, level 4.1 up to 1080p30. That is visually lossless
  and plays on older TVs and phones. YouTube downloads have come out about 2.3 times their original size.
- **Timing and audio.** `-fps_mode passthrough` keeps every frame's timestamp, and `-c:a copy` keeps the audio bit
  for bit.

## What verify.py's numbers mean

- **frames / duration:** these must equal the source's exactly. A difference means frames were dropped or added.
- **audio:** an MD5 of the copied packets must match the source's.
- **subtitle timing:** for sampled subtitles, a 200x34 px patch inside the subtitle box (scaled to the video's
  size) is compared with the source:
  - on the subtitle's first and last frames, which should differ;
  - on the frames just outside them, which should match.

  On the first run, frames with a subtitle differed by at least 59.9, and frames without one by at most 2.9. The
  pass/fail threshold is 6.
- **picture:** PSNR-Y over every frame with nothing drawn. The first run had a median of 49.4 dB. Grassy or leafy
  outdoor shots dip to about 38 dB, which is normal for CRF 16. A median under 42 means the encode went wrong.
- **macOS playback:** AVFoundation's `isPlayable`, the same check QuickTime and Finder previews use.

## Failures already met, and their fixes

- **No text filters.** Homebrew ffmpeg 9.0.2 has no libass, `subtitles` or `drawtext`. That is why the overlays are
  PNGs. Even with those filters, the PNG route gives exact control over boxes, plates and timing.
- **faster-whisper's own audio loader** fails with `TypeError: open() got an unexpected keyword argument
  'metadata_errors'` from the installed PyAV. asr.py reads the WAV with `wave` and numpy instead.
- **Kotoba-Whisper with word timestamps** crashes with `std::bad_alloc`, so the second model runs without them.
  Whisper supplies the timing.
- **Odd crop sizes.** Crops of 4:2:0 video get rounded to even sizes, so reading raw frames at an odd height
  misreads every frame. The first run's card times came out scaled by 1.5 because of this. The scripts round to
  even numbers.
- **Long ffmpeg `select` expressions.** One with hundreds of terms fails with exit code 244. The checks stream
  every frame and pick the wanted ones in Python instead.
- **Colours from JPEG frames.** These are shifted, as explained in signs.md.
- **Audio codecs MP4 can't hold** (Vorbis, PCM and others) make burn.py stop. Name the output `.mkv` instead.
- **Packet counts.** An MP4 cut without re-encoding keeps hidden packets before its first frame. The test clip had
  1835 packets but showed only 1799 frames. So frames are counted by decoding, which takes about 20 s per 30 minutes
  of 1080p.
- **Logo noise in the sheets.** A logo gets misread a dozen ways, and each misreading would start a new row.
  `ocr_tracks.for_sheets` keeps the first read of text that stays in one place, and notes how many rereads it left
  out. Rereads are similar text, or text read with confidence under 0.8. Bottom captions are never collapsed this
  way.
- **Captions revealed in steps.** A caption that grows (私は・・・ becoming 私は・・・カレー派 on the punchline) now
  starts a new row. Before that fix, the longer read was merged into the shorter track and the punchline vanished
  from the sheet.
- **The last subtitle and the end of the video.** Subtitles are clamped to the last frame. Before that fix, speech
  running to the end of a clip pushed the last subtitle past it. verify.py then failed with "could not read the
  frames".
- **The audio language tag.** YouTube downloads often tag Japanese audio as English. prepare.py prints a NOTE, and
  burn.py tags the transcribed audio stream with the spoken language unless given `--audio-lang keep`.

## Running pieces by hand

These are the ffmpeg commands the scripts wrap, for when one needs debugging:
- **Audio:** `ffmpeg -i VIDEO -map 0:a:0 -ac 1 -ar 16000 -c:a pcm_s16le mono16k.wav`
- **Frames:** `ffmpeg -i VIDEO -vf fps=2 -q:v 3 frames/%05d.jpg`. Frame n shows about (n-1) × 0.5 seconds, give or
  take a quarter second: the fps filter picks the nearest source frame.
- **Cuts:** `ffmpeg -i VIDEO -an -vf "scale=480:-2,select='gt(scene,0.22)',metadata=print:file=cuts_raw.txt" -f null -`
- **Audio check:** `ffmpeg -i FILE -map 0:a:0 -c copy -f md5 -`, run on both files. The outputs must match.
