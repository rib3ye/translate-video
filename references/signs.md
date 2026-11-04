# On-screen text: signs.tsv

Translate text that carries meaning a viewer would otherwise miss:
- Topic and title cards.
- Name and job tags.
- Notes such as "*Recorded before the series premiered".
- "From episode N" labels.
- End banners.
- Phone messages.

Skip logos, clothing, props and set dressing. Also skip the show's burned-in dialogue captions, because the
subtitles already cover the speech.

A title that sits inside a corner logo for the whole video (such as 夏の特別編, "Summer special") counts as part of the
logo. A plate covering it for half an hour would distract more than it helps. If the title matters, translate it
once in a short `caption` near the start instead.

## Finding and measuring them

- **Candidates:** sheet rows labelled `C`, `L` and `O`, and some `T` rows that aren't speech. `@(x,y)` gives the
  position as fractions of the frame.
- **Measuring:** `inspect_frame.py $WORK 152.5 --px 1000,62 1790,62` does three things:
  - It saves the exact frame as a PNG. Open it with Read.
  - It lists every text box OCR found at that moment, in pixels, as x0,y0 to x1,y1. Use these to place a plate
    over the original.
  - It prints the colour at each point you name.
- **Colours:** always measure them from that PNG, never from `frames/*.jpg`. The JPEGs decode as BT.601 and shift
  colours. The first run's cyan cards read wrong until they were measured properly, as 0,190,226.

## Timing

OCR timing is good to about half a second, which is fine for labels. For a solid-colour graphic that pops on and
off, such as a topic card, get frame-exact times:
```bash
"$PY" -I -B "$SKILL/scripts/color_spans.py" $WORK --rect 600,62,1300,2 --rgb 0,190,226
```
It prints the start and end second of every appearance, plus the graphic's left and right edges inside the strip.
Make the strip 2 px tall and lay it across a plain part of the graphic.

Three traps:
- **Two graphics in one span.** A card that is swapped for another of the same colour without leaving the screen
  comes out as one span. Run color_spans.py again with a short strip that only the longer card covers; its spans
  mark the switch.
- **Wrong edges.** Anything else of the same colour inside the strip, such as a red wall behind a red label, widens
  the reported edges. When an edge looks off, take the box from inspect_frame.py's OCR instead.
- **Text that changes inside a fixed box,** such as a name label swapped without a cut, keeps the box's colour, so
  color_spans.py can't see it. Run inspect_frame.py every 0.05 s near the OCR edges.

## Rows

Each row is `start<TAB>end<TAB>kind<TAB>text`. Coordinates and font sizes are in the video's own pixels, and `|`
breaks lines.

| Kind | Draws |
|---|---|
| `plate:x0:y0:x1:y1:size:style` | A filled box with centred bold text, shrunk to fit if needed. Use it to cover a label exactly. |
| `plate:…:style:grow-left` | The same, but the box first widens leftwards to fit the text at full size. `grow-right` and `grow` (both ways) also work. |
| `caption:x:y:size[:style]` | Outlined text with its top-left corner at x,y, where the picture should stay visible. |
| `big[:y[:size]]` | Large outlined title text centred across the frame. The default y is 64% of the height. |

Built-in styles:
- `box`: the dark subtitle box.
- `black`: near-black with a light border.
- `gold`: black with a gold border.
- `red`, `pink`, and `white` (black text).

Define a new style anywhere in the file:
```
@style cyan fill=#00BEE2 border=#000000:6 outline=#0A3C5A:1.5 radius=0
```
The settings are:
- `fill`, `text`: colours. Text defaults to white.
- `border=colour:width` and `outline=colour:width`. The outline is a stroke round the letters.
- `radius`: the corner radius.
- `bold=0` or `bold=1`.

Colours are `#RRGGBB`, or `#RRGGBBAA` for transparency.

Made-up examples on a 1920x1080 video:
```
@style cyan fill=#00BEE2 border=#000000:6 outline=#0A3C5A:1.5 radius=0
0.2	1.9	big	Tonight,
135.43	191.53	plate:926:53:1827:120:40:cyan:grow-left	What surprised you most about the trip so far?
525.0	536.5	plate:98:578:326:636:32:gold	From Ep. 4
1550.0	1555.0	caption:1380:690:40	Mio (24)|Florist
1744.0	1749.5	plate:105:742:1190:900:40:box	Coming next week:|the final episode, from Fri., Dec. 4
```

## Check

Run `render.py`, then `qa_sheet.py` at the middle of each sign. For each one, check three things:
1. Does the plate cover the original completely?
2. Can you read the text?
3. Does it collide with a subtitle?
