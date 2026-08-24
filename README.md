# Nostalgia Shorts pipeline

Automates a standalone vertical YouTube Short end to end, for nostalgia (or
any other niche), from Claude Code.

Open the folder in Claude Code and type **`/nostalgia-shorts-pipeline`**, or
just say what you want — "make me a new short", "resume \<slug\>" — and the
skill loads itself.

## Quickstart

```bash
cd pipeline
python3 preflight.py                       # always first; installs ffmpeg + the caption font if needed
python3 new_project.py my-first-short --asset-mode clips --narration none \
    --niche "nostalgia" --topic "90s mall culture"
python3 new_project.py my-first-short --audio music   # or --audio none for a silent short
```

Then follow the skill. It runs nine stages with two approval gates: you pick
the topic from ten researched ideas, and you approve the visual style off
beat 1. Everything between and after those runs without check-ins, including
the final push of the description and video to your repo (or, past GitHub's
size limit, to chat in chunks).

## What's here

| Path | What it is |
|---|---|
| `.claude/skills/nostalgia-shorts-pipeline/SKILL.md` | the skill definition — the agent's entry point |
| `PROCESS.md` | the spec, and why each rule exists |
| `playbooks/` | the editorial half: niche/topic, script, visual style, description |
| `prompts/` | the standing description prompt, used verbatim |
| `pipeline/` | the deterministic half: stdlib-only scripts |
| `projects/` | one folder per Short; media is gitignored |

## Requirements

- Python 3.9+, ffmpeg (preflight installs it), curl
- The caption font (`pipeline/fonts/`, currently Poppins Black) — preflight
  installs it into the font cache every session, no network fetch needed
- Descript MCP for the transcript SRT — narration == "full" projects only
- OpenArt MCP for the images (Nano Banana 2) or clips (Gemini Omni Flash)
- NextLev MCP is optional but makes the topic research much better

No pip installs. Everything in `pipeline/` is stdlib.

## Stage map

| # | Stage | Command |
|---|---|---|
| 1 | niche | `playbooks/01_niche_and_topic.md` |
| 2 | topic, mode, title | `new_project.py <slug> --asset-mode ... --narration ...` |
| 3 | script — narration == full only | `script_check.py <script.txt> ../projects/<slug> --fix` |
| 4 | narration + SRT — narration == full only | `audio_merge.py` then `srt_build.py` |
| 5 | scene plan | `scene_plan.py propose\|build` (full) or `scene_plan.py beats` (none) |
| 6 | visual style | `playbooks/03_visual_style.md` |
| 7 | beat batch: 7 images or 5 clips | `manifest.py init\|next\|submit\|record\|fetch\|verify\|status` |
| 7 | assemble | `assemble.py ../projects/<slug>` |
| 8 | description | `description_check.py ../projects/<slug>/description.md ../projects/<slug>/project.json` |
| 9 | deliver | `deliver.py ../projects/<slug>` |

No thumbnail stage, no highlight-clip stage — the Short itself is the only
deliverable.

## The combinations

| asset_mode | narration | audio | What it is |
|---|---|---|---|
| images | full | narration | Nano-Banana-2 stills (one per sentence, count derived from the script — not fixed), Ken Burns motion, a voiced script, word-synced captions. |
| images | none | music | 7 stills, Ken Burns motion, 4s each (28s total), scored by a music bed, no captions. |
| images | none | none | 7 stills, Ken Burns motion, 4s each (28s total), fully silent, no captions. |
| clips | full | narration | 5 Gemini Omni Flash clips, stitched, a voiced script, word-synced captions — each clip's own generated audio is stripped so it doesn't clash with the narration. |
| clips | none | clip | 5 Gemini Omni Flash clips, stitched, each clip's own native generated audio (dialogue, SFX) kept as the soundtrack, no captions. |
| clips | none | clip+music | 5 Gemini Omni Flash clips, stitched, native clip audio with a ducked music bed mixed in underneath, no captions. |

narration == "full" images shorts keep script-driven timing AND a
script-driven beat count — one beat per sentence, not a fixed 7. A longer or
more complex script produces more beats, a terser one fewer; see
`scene_plan.py`'s `propose` for exactly how (sentence cuts, short sentences
merged forward, long ones split at a comma, `IMAGES_NATURAL_MAX_BEATS` as a
safety ceiling). The fixed 7-beat / equal 28s-4s-per-beat split only applies
to narration == "none", where there's no script to derive cuts from.

Gemini Omni Flash generates synchronized audio (dialogue, SFX, music) natively
with every clip — it's not a togglable setting, so write what's said directly
into each beat's prompt (e.g. `... a woman says: "line of dialogue"`) rather
than planning for a separate voice-over pass.

Text is only ever burned in for narration == full. narration == none never
burns captions — `audio` (set via `new_project.py --audio music|none`) picks
the soundtrack: silent-or-scored for images, clip-audio-only-or-plus-music
for clips.
