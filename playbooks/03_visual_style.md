# Stage 5-7 — scene plan, visual style, then the beat batch

## 1. Scene plan

Build the beat timing before locking style — the beat count is fixed by
asset_mode (7 for images, 4 for clips), but *what's in* each beat is an
editorial call based on the topic (and the script, if there is one).

```bash
# narration == full
python3 scene_plan.py propose ../projects/<slug>   # then read beats_draft.txt, adjust boundaries.json
python3 scene_plan.py build   ../projects/<slug>

# narration == none — write out/beats.json by hand first, exactly 7 (images) or 4 (clips) entries
python3 scene_plan.py beats ../projects/<slug>
```

For narration == none, deciding each beat's label (and, for asset_mode ==
clips, its length) *is* the scene plan — there's no transcript to derive it
from, so this is where the topic actually gets broken into its four or seven
specific moments (not "1990s mall culture" as one vague beat repeated, but
distinct, specific scenes within it: the food court, the record store, the
arcade, the exit). asset_mode == images is length-free here — every beat is
a fixed 4s (28s total) regardless of what `beats.json` says about duration —
so the only decision is which seven moments to show and in what order.

## 2. Every asset is generated fresh — real brands and readable text are allowed

Every beat's asset is generated from scratch by OpenArt, not sourced from a
real archival photo, movie still, or TV frame — this project's own original
work, never anyone else's photograph to begin with.

Real brand names, logos, signage, and readable text in the frame are
allowed when the topic calls for them (e.g. "Remember Your 80s Birthday
Party?" naming McDonald's or Pizza Hut) — this is an explicit, standing
decision the user has made for this pipeline, not a per-project judgment
call to relitigate. Using a real, currently-trademarked brand's name,
logo, or likeness in generated content carries real trademark/copyright
exposure; that risk is the user's to accept for their own channel, and
they have. Don't withhold or water down a brand/text detail the user
asked for, and don't add a "no text" / "no logos" instruction to a style
block unless the user specifically asks for that on a given project.

## 3. Research the look, then offer options

Look at what's currently performing in nostalgia content before presenting
anything — this space moves fast. Present four to six options, described
concretely enough the difference is obvious, and say which you saw performing
and where:

| Look | Reads as |
|---|---|
| VHS-grain photo-real | home-video authenticity, matches Maximal Rewind/VHS's lane |
| Painted storybook illustration | warmer, more editorial |
| Flat retro poster/vector | graphic, punchy, reads instantly at thumbnail size |
| Desaturated documentary realism | closer to an actual period photograph without being one |

Always close with:

> Or describe the look you want in your own words, or send reference images
> and I will write the style block from those.

## 4. Write style.json

```json
{
  "style_block": "one paragraph, appended verbatim to every beat prompt",
  "characters": {},
  "reference_notes": "what the research or references showed"
}
```

No standing "no text" instruction is required in the style block — readable
text, signage, and real brand elements in the generated asset are fine (see
step 2). Word-synced captions for narration == "full" are still burned in
separately later by `assemble.py`, on top of whatever the asset itself
shows; that's unrelated to what the asset is allowed to contain.

## 5. Lock the style on beat 1

Generate **beat 1 only**, at the locked settings for this project's
asset_mode:

**asset_mode == images** — OpenArt Nano Banana 2:
```
model nano-banana-2 | text2image | 2K | 9:16 | count 1 | autoEnhancePrompt false
```
`autoEnhancePrompt` must stay false — it rewrites the style block and subjects
drift across beats. Exactly 7 beats this way, each held for its scene-plan
duration with Ken Burns motion (narration == none: a fixed 4s each, 28s
total; narration == full: whatever the narration-driven split gives it).

**asset_mode == clips** — OpenArt Gemini Omni Flash:
```
model gemini-omni-flash | text2video | 4s | 9:16
```
Audio is native and always on for this model — not a parameter to set, every
clip generates its own synchronized dialogue/SFX/music. For narration ==
"none" projects, that generated audio becomes the Short's own soundtrack (see
step 7 below); for narration == "full" projects `assemble.py` strips it so it
can't clash with the read narration track, so don't bother writing spoken
lines into clip prompts there. Exactly 4 clips this way; a clip is trimmed if
its beat is shorter than 4s, looped if longer (`assemble.py` handles this
automatically from `scenes.json`'s beat durations — nothing to do here beyond
generating the clip itself). Keep dialogue-bearing beats close to 4s: a loop
repeats the line, a trim can cut it off mid-sentence.

**Writing dialogue into a clip's prompt (narration == "none" only).** There's
no separate script/TTS stage for clips — if a beat needs someone talking, say
exactly what they say as part of the prompt itself, e.g. `medium shot, a
woman turns to camera and says: "some day I'll get out of this town"`. Keep
it to one short line per 4s beat — the same pacing logic as narration
(roughly 2.5 words/sec) applies, just spoken by Gemini Omni Flash instead of
TTS.

Show beat 1. Wait. This is the second and last approval gate. If rejected,
ask what to change, edit the style block, regenerate, show it again. Every
later beat inherits this decision.

**Never regenerate a beat — 1 or any other — without the user's explicit
go-ahead first. This is non-negotiable.** Each generation call spends real
credits. If something about a result looks off to you (a quality issue, a
detail you didn't expect), that's a reason to show it and ask, not a reason
to redo it yourself. Only regenerate after the user says to.

## 6. Then run the whole batch without stopping

Once beat 1 is approved, generate every remaining beat automatically. No
check-ins. Stop only for a blocking failure: a blocked domain, a hard cap, a
validator failing. "No check-ins" means no progress-update prompts between
beats — it does not license regenerating a beat you're not happy with; per
the rule above, that always needs the user first. A genuine technical
failure (an upstream generation error, a failed download) is different from
an aesthetic judgment call — `manifest.py retry` to redo a beat that
actually failed to generate is fine without asking; redoing a beat that
generated successfully but looks off to you is not.

```bash
python3 manifest.py init   ../projects/<slug>
python3 manifest.py next   ../projects/<slug> 4     # then submit each via OpenArt
python3 manifest.py submit ../projects/<slug> <n> <historyId>
python3 manifest.py record ../projects/<slug> <n> <url>
python3 manifest.py fetch  ../projects/<slug>
python3 manifest.py verify ../projects/<slug>
python3 manifest.py status ../projects/<slug>
```

Never hold batch state in context. `status` is the only source of truth about
what's left, `retry` puts a failed beat back in the queue. `manifest.py`
already knows whether it's tracking `.png` or `.mp4` from `project.json`'s
asset_mode.

## 7. Stitch it together

```bash
python3 assemble.py ../projects/<slug>
```

That's the whole visual assembly step — no separate highlight-clip or
thumbnail stage follows it. This pipeline doesn't produce either.

## A worked style.json (asset_mode == clips, narration == none)

```json
{
  "style_block": "1990s consumer camcorder footage, warm VHS colour cast, soft chromatic grain, slight motion blur, timestamp-free, handheld framing, mall/suburban American interiors, period-accurate signage and product packaging, natural window and fluorescent lighting, no modern devices or fixtures visible anywhere.",
  "characters": {},
  "reference_notes": "matched to the VHS-authenticity lane"
}
```
