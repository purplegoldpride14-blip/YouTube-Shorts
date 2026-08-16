# Nostalgia Shorts pipeline

Automates a standalone vertical YouTube Short end to end, for nostalgia (or
any other niche), from Claude Code.

Open the folder in Claude Code and type **`/nostalgia-shorts-pipeline`**, or
just say what you want — "make me a new short", "resume \<slug\>" — and the
skill loads itself.

## Quickstart

```bash
cd pipeline
python3 preflight.py                       # always first; installs ffmpeg if needed
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
- Descript MCP for the transcript SRT — narration == "full" projects only
- OpenArt MCP for the images (Nano Banana 2) or clips (Kling 2.5)
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
| 7 | beat batch: 7 images or 4 clips | `manifest.py init\|next\|submit\|record\|fetch\|verify\|status` |
| 7 | assemble | `assemble.py ../projects/<slug>` |
| 8 | description | `description_check.py ../projects/<slug>/description.md ../projects/<slug>/project.json` |
| 9 | deliver | `deliver.py ../projects/<slug>` |

No thumbnail stage, no highlight-clip stage — the Short itself is the only
deliverable.

## The combinations

| asset_mode | narration | audio | What it is |
|---|---|---|---|
| images | full | narration | 7 Nano-Banana-2 stills, Ken Burns motion, a voiced script, word-synced captions. |
| images | none | music | 7 stills, Ken Burns motion, each an equal 1/7th of a 30s timeline, scored by a music bed, no captions. |
| images | none | none | 7 stills, Ken Burns motion, each an equal 1/7th of a 30s timeline, fully silent, no captions. |
| clips | full | narration | 4 Kling 2.5 clips, stitched, a voiced script, word-synced captions. |
| clips | none | music | 4 Kling 2.5 clips, stitched, scored by a music bed, no captions — closest to a Maximal-Nostalgia-style format. |
| clips | none | none | 4 Kling 2.5 clips, stitched, fully silent, no captions. |

narration == "full" images shorts keep script-driven timing — the equal 30s
split only applies to narration == "none", where there's no audio to derive
beat lengths from.

Text is only ever burned in for narration == full. narration == none is
silent-or-scored, never captioned — `audio` (set via `new_project.py --audio
music|none`) picks which.
