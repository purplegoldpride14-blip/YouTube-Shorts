# Stage 8 — description

No thumbnail and no highlight-clip stage — this pipeline doesn't produce
either. A Short's thumbnail is whatever frame YouTube auto-selects (or the
creator picks from the finished video after upload, outside this pipeline),
and there's no long-form video to cut highlights out of in the first place —
the Short itself is the only output.

## Write description.md

Two to four sentences, not a long-form summary — a Short's description sits
under a much smaller player and a wall of text reads as a mismatch with the
format. Cover what the video actually shows: the topic/decade, the specific
angle from the ten-idea pitch back in stage 1-2. Not a generic "join us as we
explore nostalgia" line — that line fits any of a hundred videos, and it's
exactly the kind of description that makes a channel forgettable.

Use `prompts/description_prompt.txt` as the standing instruction. Feed it the
topic and the script (if there is one) or the beat labels (if there isn't).

Include `#shorts` plus two or three specific niche/decade hashtags at the end
— e.g. `#nostalgia #90small #Y2K` — unless the project has hashtags disabled
(`--hashtags` was not passed at `new_project.py` time).

## Then run

```bash
python3 description_check.py ../projects/<slug>/description.md ../projects/<slug>/project.json
```

Validates it's under YouTube's 5,000-character description cap and past this
project's own word-count floor (40 words — short, but not empty).

## Then deliver

```bash
python3 deliver.py ../projects/<slug>
```

Checks `description.md` and `out/final.mp4` exist (plus `out/captions.srt`
and the narration files, for narration == "full" projects only), mirrors the
description and narration into `out/`, and either leaves `out/final.mp4` in
place for a normal `git add -f` or splits it into chat-sized chunks if it's
over GitHub's push limit. It never touches git and never sends anything
itself — both are your call, not a scripted one.
