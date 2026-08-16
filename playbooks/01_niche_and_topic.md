# Stage 1-2 — niche, then topic, mode, and title

## 1. Ask for the niche

Present this menu. One question, one answer, always leave the door open.

> Which niche is this for?
>
> 1. Nostalgia (decades, cities, culture, trends — the likely answer)
> 2. Something else — type it
>
> You can also drop in links or screenshots of channels or videos you want
> this one to feel like, and I will read the style and topic direction off
> those instead of proposing my own.

If links or images come in, read them for: pacing, hook style, caption
placement, music-vs-voice balance, and title grammar, and let that steer the
topic proposals in step 2 toward whatever they're doing. Record what you see
in `project.json` under `notes`.

This pipeline is built around nostalgia content, but nothing in it is
hard-coded to that niche — the playbooks and prompts below are written with
nostalgia examples throughout because that's the overwhelmingly likely
answer, not because anything enforces it.

## 2. Research the niche, then propose topic ideas

For nostalgia specifically, a "topic" is a decade, a city, a subculture, or a
trend — not a single event the way a history-niche topic might be. "1990s
mall culture", "Y2K tech", "80s Miami nightlife" are topics; "the launch of
the Sony Walkman" is closer to a single beat within one.

Research before proposing — ten ideas invented from general knowledge are ten
ideas about what was popular a while ago, and this format space moves fast.

**What to look for**

- What's currently over-performing: view counts well above the channel's
  subscriber count, recent uploads still climbing.
- The angle that's saturated versus the one nobody's doing yet. Several
  channels already run the straightforward version of this idea at real
  scale (Maximal Nostalgia, Maximal Rewind, Maximal VHS among them) — a
  specific decade/city/subculture angle, or a distinctive format quirk, beats
  a generic "remember the 90s" restate of what's already out there.
- Whether Google Trends (switched to **YouTube Search**, not Web Search)
  shows a "Rising" spike for something era-adjacent — a re-release, an
  anniversary, a revival — worth riding over a generic angle with no current
  hook.

**Tools, in order of usefulness**

- NextLev MCP if connected: `search_niche_finder_channels` (nostalgia/retro/
  decade query terms), `youtube_channel_outliers` on the channels above,
  `search_viral_videos_small_channels`. Outliers from small channels are the
  strongest signal — the topic carried the video, not the subscriber base.
- Web search / Google Trends for anything current the tools don't cover.
- If neither is available, say so plainly rather than proposing from memory.

**Then present exactly ten ideas**, each a specific angle for a single Short
— a working title, the hook in one line, and one line on why it isn't the
same thing everyone else in this space is doing. Number them, end with:

> Pick a number, or write your own and I will build from that instead.

This is the first of two approval gates. Wait for the answer.

## 3. Ask for the mode

> How should this one be made?
>
> Visuals: 1. Still images (7 beats, each an equal 1/7th of 30s)   2. Motion clips (4 beats, native spoken audio via Gemini Omni Flash)
> Voice-over: 1. Full script   2. None — scored some other way

Write the answers, along with the chosen topic:

```bash
python3 new_project.py <slug> --asset-mode images|clips --narration full|none \
    --niche "nostalgia" --topic "..."
```

If voice-over is "none", also ask about the soundtrack and write it
immediately:

```bash
python3 new_project.py <slug> --audio music|none
```

For still images this is literally "music bed or fully silent." For motion
clips it's not — Gemini Omni Flash generates synchronized audio (dialogue,
SFX, music) with every clip regardless, so ask instead whether a music bed
should ALSO be mixed in underneath that generated audio ("music") or not
("none"); there's no fully-silent option for clips.

## 4. Pick the title

Off the chosen topic, not later. Propose three to five options grounded in
the specific angle rather than a generic decade label, and close with:

> Pick a number, or write your own title.

Save it immediately:

```bash
python3 new_project.py <slug> --title "..."
```
