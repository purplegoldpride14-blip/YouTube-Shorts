---
name: nostalgia-shorts-pipeline
description: >
  Produce a standalone vertical YouTube Short end to end - niche and topic
  selection, mode selection (still images or motion clips, voiced or
  unvoiced), script (if voiced), narration audio, aligned SRT (if voiced),
  scene plan, visual style, beat batch (7 images via Nano Banana 2, or 5
  clips via Gemini Omni Flash with native audio), assembly, and description.
  No thumbnail, no
  highlight-clip stage - the Short itself is the only deliverable. Use when
  the user wants to make a new nostalgia (or other niche) Short, resume an
  interrupted one, or run any single stage. Trigger on "new short", "make a
  short", "resume <slug>", or a request to write a Short script, build an
  SRT, plan beats, assemble a Short, or write a Short's description.
---

# Nostalgia Shorts pipeline

Every path below is relative to the repository root, not to this file.

Read `PROCESS.md` before starting. Every number lives in `pipeline/config.py`;
the docs describe it and never override it.

## Always run first

```bash
cd pipeline && python3 preflight.py
```

Installs ffmpeg if missing, installs the bundled caption font
(`pipeline/fonts/`) into the font cache and verifies it resolves correctly,
checks the domain allowlist. If a domain is blocked, STOP and tell the user -
the allowlist is fixed at session start and can't be changed mid-run. If the
font check fails, STOP and tell the user too - the fallback would render
captions in the wrong typeface instead of loudly breaking.

## Two approval gates, nothing else

**Gate 1 — topic.** Ask for the niche (likely nostalgia), research what's
over-performing in it, propose exactly ten ideas, wait for the pick.

**Gate 2 — style.** Offer visual styles that are working right now, write the
style block, generate beat 1 only at locked settings, show it, wait for
approval.

Between and after these, run without check-ins. Once beat 1 is approved,
generate the rest of the fixed-count batch automatically, no continuation
prompts. There is no thumbnail check and no highlight-clip stage - this
pipeline doesn't produce either.

**Never regenerate any beat without the user's explicit go-ahead first -
non-negotiable.** Every generation call spends real credits. Noticing a
quality issue, an unwanted detail, or anything else that gives you pause
about a result is a reason to show it to the user and ask, never a reason
to redo it on your own judgment. This applies at every stage, not just gate
2. The one exception: `manifest.py retry` on a beat that genuinely failed
to generate (an upstream error, a failed download) is bookkeeping, not a
judgment call, and doesn't need to wait for authorization.

## Stage sequence

1. **Niche.** `playbooks/01_niche_and_topic.md`. Menu (nostalgia, or
   something else) plus a write-in option; accept reference images or links.
2. **Topic and mode.** Research the niche for what's currently
   over-performing, propose ten topic ideas (a decade/city/subculture/trend,
   not a single event), wait for the pick. Then ask for asset_mode
   (images/clips) and narration (full/none) and write both immediately:
   `new_project.py <slug> --asset-mode images|clips --narration full|none --niche "..." --topic "..."`
   If narration == "none", also ask about the soundtrack and write it
   immediately: `new_project.py <slug> --audio music|none`. asset_mode ==
   "images": music bed or fully silent. asset_mode == "clips" (Gemini Omni
   Flash generates its own audio with every clip, always): "music" mixes a
   ducked bed in underneath the clips' own audio, "none" is clip audio alone
   - never literal silence.
   Propose three to five titles off the chosen topic and save one before
   moving on - don't defer this to the description stage.
3. **Script — narration == "full" only.** `playbooks/02_script.md`. 80-115
   words, averaging 30-45s. Then:
   `python3 script_check.py <script.txt> ../projects/<slug> --fix`
   As soon as this passes, commit and push `script.txt` and
   `narration_part1.txt` before asking the user to generate audio - they need
   it pulled from the repo to hand to OpenArt.
   If narration == "none", skip straight to stage 5.
4. **Narration — narration == "full" only.** The user generates the audio with
   OpenArt's own "Create Voice Over" feature (ElevenLabs voices, in the
   OpenArt app - not reachable through the OpenArt MCP tools available here,
   only `openart_generate_image`/`openart_generate_video` are) and drops the
   file(s) in `projects/<slug>/audio/`. Then:
   `python3 audio_merge.py ../projects/<slug>/audio ../projects/<slug>`
   Import that same file to Descript as a composition via the Descript MCP,
   export one SRT into `projects/<slug>/srt/`. Then:
   `python3 srt_build.py ../projects/<slug>/srt ../projects/<slug>`
5. **Scene plan.**
   - narration == "full": `python3 scene_plan.py propose ../projects/<slug>`,
     read `beats_draft.txt`, adjust `boundaries.json` if a cut lands badly,
     then `python3 scene_plan.py build ../projects/<slug>`. asset_mode ==
     "clips" always produces exactly 5 beats - never more, never fewer.
     asset_mode == "images" is different: the count isn't fixed, it's
     derived - one beat per sentence (natural cuts), so a longer or more
     complex script gets more beats and a terser one gets fewer
     (`IMAGES_NATURAL_MAX_BEATS` caps runaway fragmentation from an
     unusually staccato script). Timing still comes from the actual
     narration length here, not an equal split.
   - narration == "none": write `out/beats.json` by hand, exactly 7 (images)
     or 5 (clips) entries - this is where the topic actually becomes five or
     seven specific moments, not one vague beat repeated. asset_mode ==
     "images": each entry only needs `{"label": "..."}` - duration is always
     a fixed 4s (28s total; `scene_plan.py beats` computes it and ignores any
     `"dur"` you write), so don't propose per-beat durations to the user,
     only labels. asset_mode == "clips": still state
     `{"label": "...", "dur": ...}` per entry by hand, same as before - keep
     durations close to 4s (`VIDEO_CLIP_SEC`) for any beat that needs
     dialogue, since a loop repeats the line and a trim can cut it off.
     Labels are planning/description material only - narration == "none"
     never burns text into the video, so don't present them to the user as
     captions-to-be. Then `python3 scene_plan.py beats ../projects/<slug>`.
     If `audio` was set to "music", also drop a bed into
     `projects/<slug>/audio/music.<ext>` before assembly - this pipeline
     doesn't generate or license music itself. If `audio` is "none", nothing
     to do here.
6. **Style.** `playbooks/03_visual_style.md`. Offer options, accept a
   write-in or reference images, write `style.json`. Every asset is
   generated fresh by OpenArt, not sourced from a real photo/frame - but
   real brand names, logos, signage, and readable text in the generated
   asset are allowed when the topic calls for them (standing user
   decision, not a per-project call).
7. **Beat 1, then the batch.** Generate beat 1 alone at locked settings -
   `nano-banana-2 | text2image | 2K | 9:16` for images,
   `gemini-omni-flash | text2video | 4s | 9:16` for clips (native audio,
   always on - not a parameter). For clips + narration == "none", write the
   spoken line directly into the beat's prompt (e.g. `...says: "line"`) if
   that beat needs dialogue; for narration == "full" clips, don't - the
   clip's own audio gets stripped at assembly so it never plays. Show beat 1,
   wait for approval (gate 2), then write `prompts.json` mapping beat number
   to prompt and run the batch to completion, autonomously:
   `manifest.py init / next / submit / record / fetch / verify / status`,
   in a loop, until `status` says all done. Never hold batch state in
   context - `status` is the source of truth.
8. **Assemble.** `python3 assemble.py ../projects/<slug>`. Branches
   automatically on `project.json`'s asset_mode/narration/audio - Ken Burns
   stills or trimmed/looped clips; word-synced captions from
   `out/captions.srt` for narration == "full", no burned text at all for
   narration == "none". Audio source: narration == "full" uses the narration
   track (clips' own audio stripped); narration == "none" + images uses
   `audio` (music bed or none) alone; narration == "none" + clips keeps each
   clip's own generated audio as the primary track and only uses `audio` to
   decide whether a ducked music bed is mixed in underneath it. Refuses to
   run for a narration == "none" project until `audio` is set. Nothing to
   choose here beyond running it. Captions burn in Poppins Black (`FONT`,
   bundled in `pipeline/fonts/` and installed by `preflight.py` every
   session - see "Always run first" above), large (`FONT_SIZE` 84px) and
   well above the bottom of the frame (`CAPTION_MARGIN_V_FRAC` 0.45 of
   `OUT_HEIGHT` up from the bottom edge) - YouTube's own Shorts UI (title,
   handle, description, like/comment/share rail) covers roughly the bottom
   quarter to third of the player once uploaded, and that overlay isn't
   present in the raw file assembled here.
9. **Description, then deliver.** `playbooks/04_description.md`. Use
   `prompts/description_prompt.txt`, base it on the script (if any) or the
   beat labels, then `description_check.py`. Once it passes:
   `python3 deliver.py ../projects/<slug>`
   Verifies `description.md` and `out/final.mp4` exist (plus
   `out/captions.srt` and the narration file, for narration == "full"
   projects only), mirrors the description and narration into `out/`, checks
   `out/final.mp4` against `GIT_PUSH_MAX_BYTES`. `out/` is gitignored by
   default, so this always needs `-f`:
   - **Under the limit:** git-add the file as-is.
   - **Over the limit:** `deliver.py` splits it into `<name>.part_NNN` files
     under `out/chunks/` and writes a `.sha256` next to them. Never git-add
     the oversized original. Send the chunks via chat with the sha256 and
     reassembly command (`cat <name>.part_* > <name>`).
   `deliver.py`'s own output lists exactly which paths are git-addable and
   which need chat delivery - follow it rather than reconstructing the list.
   This is bookkeeping, not judgement - do it without asking.

## Resuming

`python3 manifest.py status ../projects/<slug>` reports exactly what remains.
Downloaded frames/clips persist. Never regenerate a beat already marked done.
