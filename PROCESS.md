# PROCESS — nostalgia Shorts pipeline

Adapted from a parent pipeline that built one 11-minute narrated video per
run. This one builds standalone vertical Shorts, one per run, following nine
fixed stages:

1. Niche (nostalgia, or something else)
2. Topic (a decade, city, subculture or trend — or a reference upload)
3. Script, only if narration is wanted (30-45s average)
4. Descript SRT, only if there's a script
5. Scene plan, from the topic or the script
6. Beat batch: 4 motion clips (Kling 2.5) or 5 still images (Nano Banana 2)
7. Stitch
8. Description
9. Deliver — no thumbnail, no highlight clips

The judgement/arithmetic split carries over from the parent pipeline
unchanged:

- **Judgement** — niche, topic, script (if any), beat content and timing,
  visual style. Stays with the agent.
- **Arithmetic** — offsets, timing, encoding, validation. Lives in
  `pipeline/`, runs identically every time, fails loudly.

> Every number in this document describes `pipeline/config.py`. If they ever
> disagree, config.py wins.

---

## The four combinations

| asset_mode | narration | audio | What it is |
|---|---|---|---|
| images | full | (narration track) | 5 stills, Ken Burns motion, a voiced script under it, word-synced captions. |
| images | none | music | 5 stills, Ken Burns motion, silent — no captions, no beat labels — scored by a music bed. |
| images | none | none | 5 stills, Ken Burns motion, fully silent, no captions. |
| clips | full | (narration track) | 4 Kling clips, stitched, a voiced script under it, word-synced captions. |
| clips | none | music | 4 Kling clips, stitched, scored by a music bed, no captions — closest to Maximal Nostalgia's format. |
| clips | none | none | 4 Kling clips, stitched, fully silent, no captions. |

asset_mode and narration are both set once, in `new_project.py`, and read by
every later stage. `audio` is set the same way, but only matters for
narration == none — a narration == full project's only audio is its
narration track. Nothing branches on a command-line flag past that point.

**No narration means no burned text, full stop.** The old "beat-labeled
captions over music" behaviour is gone — narration == none produces a
silent-or-scored video with nothing burned into the frame. Beat labels in
`beats.json` are still required (they're how the topic gets broken into its
four or five specific moments), they're just never rendered.

---

## Run order

```bash
cd pipeline
python3 preflight.py                                     # FIRST. Always.
python3 new_project.py <slug> --asset-mode images|clips --narration full|none \
    --niche "nostalgia" --topic "..."
# narration == none only: also set the soundtrack
python3 new_project.py <slug> --audio music|none

# ---- narration == full ----
# after writing script.txt
python3 script_check.py <script.txt> ../projects/<slug> --fix
# after the user drops voice-over files into projects/<slug>/audio/
python3 audio_merge.py ../projects/<slug>/audio ../projects/<slug>
# after exporting a raw SRT from Descript into projects/<slug>/srt/
python3 srt_build.py ../projects/<slug>/srt ../projects/<slug>
python3 scene_plan.py propose ../projects/<slug>
python3 scene_plan.py build   ../projects/<slug>

# ---- narration == none ----
# write out/beats.json by hand: exactly 5 (images) or 4 (clips) entries,
# [{"label": "...", "dur": ...}, ...] — labels are bookkeeping only, never burned
python3 scene_plan.py beats ../projects/<slug>
# if audio == music: drop a music bed into projects/<slug>/audio/music.<ext>
# if audio == none: nothing to do here, assemble.py produces a silent video

# ---- both paths converge here ----
python3 manifest.py init   ../projects/<slug>
python3 manifest.py next   ../projects/<slug> 4
python3 manifest.py submit ../projects/<slug> <n> <historyId>
python3 manifest.py record ../projects/<slug> <n> <url>
python3 manifest.py fetch  ../projects/<slug>
python3 manifest.py verify ../projects/<slug>

python3 assemble.py ../projects/<slug>
python3 description_check.py ../projects/<slug>/description.md ../projects/<slug>/project.json
python3 deliver.py ../projects/<slug>
```

---

## Approval gates

1. **Topic.** Ten researched ideas, or the user's own. Human picks.
2. **Style.** Beat 1 generated alone at locked settings. Human approves.

That's both of them. No thumbnail gate — there's no thumbnail stage.

Everything else runs without check-ins. Stop mid-run only for a blocking
failure: a domain not allowlisted, a hard cap exceeded, a validator failing.

---

## The numbers, and why

**Beat count: fixed at 5 for images, 4 for clips — never derived.** The
parent pipeline algorithmically cut scenes from sentence novelty and target
pacing; this pipeline doesn't. A script's timing bends to fit the fixed
count (beats land at the nearest sentence end to an even N-way split of the
total duration); the count itself never varies with how the script happens to
be written, and narration == none states the count directly since there's no
script to derive anything from.

**Script (narration == full): 80-115 words, hard band 65-130.** Averages
30-45s of narration at this pipeline's tested pace of ~2.5-2.6 words/sec.

**Images: OpenArt Nano Banana 2, text2image, 2K, 9:16, `autoEnhancePrompt`
always false.** Unchanged from the parent pipeline's image settings except
the aspect ratio — 9:16 native instead of 16:9, since this pipeline never
crops or letterboxes downstream.

**Clips: OpenArt Kling 2.5, quality mode, 5 seconds, audio off, 9:16.** Audio
off because the clip's own generated audio is never used — this pipeline's
narration or music track is the only audio in the final output. A beat
shorter than 5s trims the clip; a beat longer loops it
(`-stream_loop -1 -t <beat_dur>`). Clips never get Ken Burns — motion is
already baked into the source.

**Output: 1080x1920 native, no letterbox/crop step.** Generated vertical from
the first frame at both `IMAGE_ASPECT`/`VIDEO_ASPECT` — nothing to reframe
downstream, and no separate long-form master to cut Shorts out of afterward.

**Duration: floor 15s (WARN), soft max 90s (WARN), hard max 180s (FAIL).**
The hard max is YouTube's actual Shorts technical cap. 4 clips at 5s each is
20s if played straight with no narration to stretch the beats — comfortably
inside the floor.

**Captions: word-synced, narration == full only.** Full narration burns
`out/captions.srt`, aligned the same way the parent pipeline does it.
narration == none burns nothing — no word captions, no beat-labeled title
cards, no text of any kind. `beats.json` labels exist for planning and the
description stage only.

**Audio (narration == none): `music` or `none`, set on `project.json`.**
`music` loops/trims `audio/music.*` to the total beat duration at -23 LUFS —
this pipeline doesn't generate or license music, so a file has to be placed
there before `assemble.py` will run. `none` produces a video with no audio
stream at all. `assemble.py` refuses to run for a narration == none project
until `audio` is set to one or the other.

**Volume (narration == full): -14 LUFS, true peak -1.5 dB** — unchanged from
the parent pipeline, because the physics of what sounds right on a phone
speaker didn't change just because the video got shorter.

**Description: 40-word floor, YouTube's 5,000-character cap.** Two to four
sentences in practice — a Short's description isn't a long-form summary.

---

## What the parent pipeline had that this one doesn't

- **No thumbnail stage, no thumbnail approval gate, no `thumbnail_prompt.txt`.**
  Dropped entirely, per spec — a Short's thumbnail is whatever YouTube
  auto-selects or the creator picks post-upload, outside this pipeline.
- **No `make_shorts.py` / highlight-clip stage.** The Short itself is the
  only output; there's no long-form master to cut moments out of.
- **No sentence-novelty scene-cutting algorithm.** Replaced by the fixed
  beat count above — simpler, and matches how this pipeline is actually meant
  to run.
