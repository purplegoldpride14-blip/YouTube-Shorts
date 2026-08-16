# Stage 5-7 — scene plan, visual style, then the beat batch

## 1. Scene plan

Build the beat timing before locking style — the beat count is fixed by
asset_mode (5 for images, 4 for clips), but *what's in* each beat is an
editorial call based on the topic (and the script, if there is one).

```bash
# narration == full
python3 scene_plan.py propose ../projects/<slug>   # then read beats_draft.txt, adjust boundaries.json
python3 scene_plan.py build   ../projects/<slug>

# narration == none — write out/beats.json by hand first, exactly 5 or 4 entries
python3 scene_plan.py beats ../projects/<slug>
```

For narration == none, deciding each beat's label and length *is* the scene
plan — there's no transcript to derive it from, so this is where the topic
actually gets broken into its four or five specific moments (not "1990s mall
culture" as one vague beat repeated four times, but four distinct, specific
scenes within it: the food court, the record store, the arcade, the exit).

## 2. Original art only — never a reproduction

Every beat's asset is generated from scratch by OpenArt, not sourced from a
real archival photo, movie still, or TV frame. This isn't just a style
choice: a real photo from any recent-enough decade is still under active
copyright and often still commercially licensed even decades later; an image
or clip generated fresh from a text prompt is this project's own original
work and was never anyone else's photograph to begin with.

This means the style block should describe a look, a mood, a palette — not
instruct the model to recreate a specific known photograph, film frame, or
album cover, and asking it to render a specific real, currently-trademarked
logo is worth avoiding the same way. "1980s mall arcade, neon glow, VHS
grain" is fine. "The cover of [a specific named album]" is not.

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

End the style block with `no text anywhere in the image` — for narration ==
"full", word-synced captions are burned in later by `assemble.py` as a
separate overlay, not baked into the asset. For narration == "none",
`assemble.py` burns no text at all, so there's even less reason for the
generated asset to carry any.

## 5. Lock the style on beat 1

Generate **beat 1 only**, at the locked settings for this project's
asset_mode:

**asset_mode == images** — OpenArt Nano Banana 2:
```
model nano-banana-2 | text2image | 2K | 9:16 | count 1 | autoEnhancePrompt false
```
`autoEnhancePrompt` must stay false — it rewrites the style block and subjects
drift across beats. Exactly 5 beats this way, each held for its scene-plan
duration with Ken Burns motion.

**asset_mode == clips** — OpenArt Kling 2.5:
```
model Kling 2.5 | quality mode | 5s | audio off | 9:16
```
Audio off because this pipeline's own narration or music track is the only
audio in the final output — a clip's own generated audio would clash with it
or get discarded either way, so don't spend the generation on it. Exactly 4
clips this way; a clip is trimmed if its beat is shorter than 5s, looped if
longer (`assemble.py` handles this automatically from `scenes.json`'s beat
durations — nothing to do here beyond generating the clip itself).

Show beat 1. Wait. This is the second and last approval gate. If rejected,
ask what to change, edit the style block, regenerate, show it again. Every
later beat inherits this decision.

## 6. Then run the whole batch without stopping

Once beat 1 is approved, generate every remaining beat automatically. No
check-ins. Stop only for a blocking failure: a blocked domain, a hard cap, a
validator failing.

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
  "style_block": "1990s consumer camcorder footage, warm VHS colour cast, soft chromatic grain, slight motion blur, timestamp-free, handheld framing, mall/suburban American interiors, period-accurate signage and product packaging rendered as generic unbranded shapes rather than real logos, natural window and fluorescent lighting, no modern devices or fixtures visible anywhere, no text anywhere in the frame.",
  "characters": {},
  "reference_notes": "matched to the VHS-authenticity lane; period signage kept generic/unbranded rather than reproducing real store or product logos"
}
```
