# Stage 3 — the script (narration == "full" only)

If this project's narration is "none", skip this entire stage — there is no
script. Go straight to writing `out/beats.json` by hand (see PROCESS.md's run
order) and pick up again at the manifest stage.

Averages 30-45 seconds of narration — 80-115 words at this pipeline's tested
pace of roughly 2.5-2.6 words/sec, enforced by `script_check.py`, which also
strips anything the voice-over would stumble on. There's no room here for a
slow open or a summary close; every sentence has to earn its place.

## Structure

A Short doesn't have separate movements the way an 11-minute video does —
there usually isn't time for more than one. Think of it as a single small arc:

**First sentence — already inside it.** No "picture this", no channel intro.
Open mid-scene, specific enough that the viewer knows exactly when and where
they are within the first three words. "The mall arcade in 1985 smelled like
carpet cleaner and quarters" — not "let's talk about 80s arcades."

**Middle — one sensory or specific detail, then one more.** Two, not four. A
Short's whole runtime is what an 11-minute video spends on its cold open, so
there's no room for a list. Pick the two details that do the most work and
cut everything else, including good material — this is where the discipline
actually lives.

**Last line — a landing, not a summary.** End on the single most quotable
line, ideally one that closes the scene rather than explaining it. No
"like and subscribe" in the narration; that's a caption/description job, not
a narration one.

## What's different from long-form retention writing

- **No re-hook cadence.** A Short is one hook, sustained, not a series of
  re-hooks spaced through an 11-minute runtime.
- **Second person still helps, but there's only room for it once.** Spend it
  on the first sentence.
- **Specific still beats general** — "quarters" and "1985" hold; "back in the
  day" does not.
- **Read it aloud against a stopwatch before running script_check.py.** 80-115
  words is a target band, not a guarantee of the right *feel* — a script that
  hits the count but reads slow on the ear needs cutting regardless of what
  the counter says.

## Narration safety

The voice-over reads literally, so `script_check.py --fix` auto-fixes dashes,
ranges, symbols and abbreviations, and flags bare numerals, ALL-CAPS,
currency, roman numerals, and URLs for you to rewrite by hand.

## Then run

```bash
python3 script_check.py <script.txt> ../projects/<slug> --fix
```

Hard-fails outside 65-130 words, warns outside 80-115. A Short's script is
always one TTS part in practice — the 10,000-character split logic only ever
matters if you've written something long enough that it's no longer really a
Short.
