#!/usr/bin/env python3
"""
Plan the beats — this pipeline's word for what the parent pipeline calls
"scenes". Renamed because narration == "none" shorts have no script to cut
on, and because the count here is fixed, not derived.

asset_mode == "clips" always has exactly CLIPS_PER_SHORT (5) beats, and
asset_mode == "images" with narration == "none" always has exactly
IMAGES_PER_SHORT (7) — both fixed regardless of what the script/beats.json
says, a deliberate simplification over the parent pipeline's sentence-novelty
cutting algorithm.

asset_mode == "images" with narration == "full" is the one case where the
count is NOT fixed — it's derived from the script itself: one beat per
sentence (a natural cut point), so a longer or more complex script produces
more beats and a terser one produces fewer, rather than bending an arbitrary
fixed count to fit. See propose() below for exactly how.

Two branches, chosen by project.json's narration field:

  narration == "full"    (propose / build)
    propose   Reads out/words.json and out/audio_meta.json.
              asset_mode == "clips": splits the total duration into
              CLIPS_PER_SHORT even target windows and snaps each internal
              boundary to the nearest sentence end (or, failing that, the
              nearest word) near its target — so cuts land on the audio
              without landing mid-sentence.
              asset_mode == "images": cuts at every sentence end, merges a
              sentence that alone would fall under BEAT_MIN_SEC into its
              neighbor, and splits one that alone would run over
              BEAT_SOFT_MAX_SEC at the nearest comma — natural cuts, not a
              fixed count. IMAGES_NATURAL_MAX_BEATS caps runaway
              fragmentation from an unusually staccato script.
              Either way, writes a draft boundaries.json plus a readable
              beats_draft.txt.
    build     Reads boundaries.json (the draft, or your edit of it).
              asset_mode == "clips": validates it has exactly
              CLIPS_PER_SHORT boundaries. asset_mode == "images": validates
              it's sorted, unique, and in range — whatever count propose()
              (or your edit) produced is the count. Writes out/scenes.json.

  narration == "none"    (beats)
    beats     Reads out/beats.json — a hand-written list of exactly N
              [{"label": "..."}, ...] entries (asset_mode == "clips" also
              states "dur" per entry). asset_mode == "images" beats are
              always equal-length — IMAGES_TOTAL_DURATION_SEC split evenly
              across IMAGES_PER_SHORT, any "dur" in beats.json is ignored —
              so the only editorial call left is each beat's label.
              asset_mode == "clips" beats keep their own hand-stated "dur",
              same as before. Validates the count and durations and writes
              out/scenes.json in the same shape as the narrated branch, so
              manifest.py and assemble.py don't care which branch produced
              it.

Usage:
    python3 scene_plan.py propose <project_dir>          # narration == full
    python3 scene_plan.py build   <project_dir>           # narration == full
    python3 scene_plan.py beats   <project_dir>            # narration == none
"""
import sys
import os
import re
import json
import argparse

from config import (IMAGES_PER_SHORT, CLIPS_PER_SHORT, BEAT_MIN_SEC,
                    BEAT_SOFT_MAX_SEC, BEAT_HARD_MAX_SEC, DURATION_MIN_SEC,
                    DURATION_SOFT_MAX_SEC, DURATION_HARD_MAX_SEC,
                    IMAGES_TOTAL_DURATION_SEC, IMAGES_NATURAL_MAX_BEATS)

SENT_END = re.compile(r"[.!?]$")
COMMA_END = re.compile(r",$")


def _asset_mode(project_dir):
    proj = json.load(open(os.path.join(project_dir, "project.json")))
    mode = proj.get("asset_mode")
    if mode not in ("images", "clips"):
        print(f"FAIL: project.json asset_mode is {mode!r}, must be 'images' or 'clips'")
        sys.exit(1)
    return mode


def fixed_count(project_dir):
    mode = _asset_mode(project_dir)
    return IMAGES_PER_SHORT if mode == "images" else CLIPS_PER_SHORT


# ---------------- narration == "full" branch ----------------

def load_words(project_dir):
    return json.load(open(os.path.join(project_dir, "out", "words.json")))


def sentence_ends(words):
    """Word indices (0-based) that end a sentence — the preferred cut points."""
    return {i for i, w in enumerate(words) if SENT_END.search(w["w"])}


def _fixed_starts(words, audio_dur, n):
    """asset_mode == 'clips': n even target windows, each snapped to the
    nearest sentence end (or, failing that, the nearest word)."""
    ends = sentence_ends(words)
    # word start-indices right after a sentence end - the candidate cut points
    candidates = sorted(i + 1 for i in ends if i + 1 < len(words))

    starts = [0]
    for k in range(1, n):
        target_t = audio_dur * k / n
        pool = [c for c in candidates if c not in starts]
        if pool:
            best = min(pool, key=lambda c: abs(words[c]["start"] - target_t))
        else:
            # no sentence-end left unused - fall back to the nearest free word
            best = min((i for i in range(1, len(words)) if i not in starts),
                       key=lambda c: abs(words[c]["start"] - target_t))
        starts.append(best)
    starts = sorted(set(starts))

    # a fallback pass can occasionally collapse two targets onto the same
    # candidate - pad back out to n by inserting the next-best unused word
    while len(starts) < n:
        gaps = [(starts[i + 1] - starts[i], i) for i in range(len(starts) - 1)]
        _, i = max(gaps)
        mid = (starts[i] + starts[i + 1]) // 2
        if mid in starts:
            mid += 1
        starts.insert(i + 1, mid)
        starts = sorted(set(starts))

    return starts


def _natural_starts(words, audio_dur):
    """asset_mode == 'images', narration == 'full': one beat per sentence -
    the count is derived from the script, not fixed. A sentence that alone
    would fall under BEAT_MIN_SEC merges into its neighbor; a segment that
    ends up over BEAT_SOFT_MAX_SEC (one long sentence, or several short ones
    that had to merge) gets split at the nearest comma to its midpoint, or
    the nearest word if there's no comma. IMAGES_NATURAL_MAX_BEATS is a
    safety ceiling, not a target - see config.py."""
    ends = sentence_ends(words)
    candidates = sorted(i + 1 for i in ends if i + 1 < len(words))

    # pass 1: accept a sentence-end cut only once the segment since the last
    # accepted cut clears BEAT_MIN_SEC - a too-short sentence merges forward.
    starts = [0]
    cur_t = 0.0
    for c in candidates:
        t = words[c]["start"]
        if t - cur_t >= BEAT_MIN_SEC:
            starts.append(c)
            cur_t = t
    # the trailing segment needs the same floor - drop the last cut if it
    # leaves too little at the end, merging it back into the prior segment.
    while len(starts) > 1 and (audio_dur - words[starts[-1]]["start"]) < BEAT_MIN_SEC:
        starts.pop()

    # pass 2: split any segment still over BEAT_SOFT_MAX_SEC at the nearest
    # comma to its midpoint (or nearest word, if no comma), as long as both
    # halves would still clear BEAT_MIN_SEC. Restart the scan after each
    # split since indices shift; stop once a full pass makes no change.
    changed = True
    while changed:
        changed = False
        for i in range(len(starts)):
            s = starts[i]
            t0 = words[s]["start"]
            end_t = words[starts[i + 1]]["start"] if i + 1 < len(starts) else audio_dur
            if end_t - t0 <= BEAT_SOFT_MAX_SEC:
                continue
            span_end = starts[i + 1] if i + 1 < len(starts) else len(words)
            span = [w for w in range(s + 1, span_end) if w not in starts]
            if not span:
                continue
            target_t = t0 + (end_t - t0) / 2
            commas = [w for w in span if COMMA_END.search(words[w - 1]["w"])]
            pool = commas or span
            best = min(pool, key=lambda c: abs(words[c]["start"] - target_t))
            if (words[best]["start"] - t0) < BEAT_MIN_SEC or (end_t - words[best]["start"]) < BEAT_MIN_SEC:
                continue
            starts.append(best)
            starts = sorted(set(starts))
            changed = True
            break

    # safety cap: repeatedly merge whichever adjacent pair of beats would
    # produce the shortest combined segment, until at or under
    # IMAGES_NATURAL_MAX_BEATS - keeps an unusually staccato script from
    # fragmenting into an excessive number of paid image generations.
    while len(starts) > IMAGES_NATURAL_MAX_BEATS:
        best_i, best_dur = None, None
        for i in range(1, len(starts)):
            t0 = words[starts[i - 1]]["start"]
            t1 = words[starts[i + 1]]["start"] if i + 1 < len(starts) else audio_dur
            merged = t1 - t0
            if best_dur is None or merged < best_dur:
                best_dur, best_i = merged, i
        starts.pop(best_i)

    return starts


def propose(project_dir):
    words = load_words(project_dir)
    meta = json.load(open(os.path.join(project_dir, "out", "audio_meta.json")))
    audio_dur = meta["duration_sec"]
    mode = _asset_mode(project_dir)

    if mode == "clips":
        n = CLIPS_PER_SHORT
        if n > len(words):
            print(f"FAIL: {n} beats requested but the script is only {len(words)} words")
            return 1
        starts = _fixed_starts(words, audio_dur, n)
        method = "fixed count"
    else:
        starts = _natural_starts(words, audio_dur)
        method = "natural cuts"

    bounds = [s + 1 for s in starts]  # 1-based word indices, build()'s format
    bp = os.path.join(project_dir, "boundaries.json")
    json.dump({"boundaries": bounds}, open(bp, "w"), indent=1)

    draft = os.path.join(project_dir, "beats_draft.txt")
    with open(draft, "w", encoding="utf-8") as f:
        for i, s in enumerate(starts, 1):
            end = (starts[i] - 1) if i < len(starts) else len(words) - 1
            t0 = words[s]["start"]
            t1 = words[starts[i]]["start"] if i < len(starts) else audio_dur
            txt = " ".join(w["w"] for w in words[s:end + 1])
            f.write(f"[{i:03d}] {t0:6.2f}s - {t1:6.2f}s ({t1-t0:5.2f}s)\n")
            f.write(f"      {txt}\n\n")

    print(f"OK  proposed {len(starts)} beat(s) ({method} for this asset_mode)")
    print(f"    wrote {bp}")
    print(f"    wrote {draft}   <- read this, adjust boundaries.json, then run build")
    return 0


def build(project_dir):
    words = load_words(project_dir)
    meta = json.load(open(os.path.join(project_dir, "out", "audio_meta.json")))
    mode = _asset_mode(project_dir)
    B = json.load(open(os.path.join(project_dir, "boundaries.json")))["boundaries"]

    if mode == "clips":
        n = CLIPS_PER_SHORT
        if len(B) != n:
            print(f"FAIL: boundaries.json has {len(B)} entries, this project needs exactly {n}")
            return 1
    else:
        n = len(B)  # images + full: derived count, not fixed - see propose()

    if B != sorted(B) or len(set(B)) != len(B):
        print("FAIL: boundaries must be sorted and unique")
        return 1
    if B[0] != 1:
        print("FAIL: the first boundary must be word 1")
        return 1
    if B[-1] > len(words):
        print(f"FAIL: boundary {B[-1]} exceeds the word count {len(words)}")
        return 1

    scenes = []
    for i, b in enumerate(B):
        end_w = (B[i + 1] - 2) if i + 1 < len(B) else len(words) - 1
        scenes.append({
            "n": i + 1,
            "start": words[b - 1]["start"],
            "end": words[end_w]["end"],
            "text": " ".join(w["w"] for w in words[b - 1:end_w + 1]),
        })

    for i in range(len(scenes) - 1):
        scenes[i]["end"] = scenes[i + 1]["start"]
    scenes[0]["start"] = 0.0
    scenes[-1]["end"] = meta["duration_sec"]
    for s in scenes:
        s["dur"] = round(s["end"] - s["start"], 4)

    return _validate_and_write(project_dir, scenes, meta["duration_sec"], n)


# ---------------- narration == "none" branch ----------------

def beats(project_dir):
    """Build scenes.json directly from a hand-written out/beats.json — exactly
    the fixed count for this asset_mode. asset_mode == "images" beats are
    always equal-length (IMAGES_TOTAL_DURATION_SEC / IMAGES_PER_SHORT each),
    so only "label" is required; asset_mode == "clips" beats keep their own
    hand-stated "dur"."""
    n = fixed_count(project_dir)
    mode = json.load(open(os.path.join(project_dir, "project.json"))).get("asset_mode")
    beats_path = os.path.join(project_dir, "out", "beats.json")
    if not os.path.exists(beats_path):
        example = ('[{"label": "arcade cabinet, 1988"}, ...]' if mode == "images"
                   else '[{"label": "arcade cabinet, 1988", "dur": 5.0}, ...]')
        print(f"FAIL: {beats_path} not found. Write it first, exactly {n} entries: {example}")
        return 1
    raw = json.load(open(beats_path))
    if len(raw) != n:
        print(f"FAIL: beats.json has {len(raw)} entries, this project needs exactly {n}")
        return 1

    equal_dur = IMAGES_TOTAL_DURATION_SEC / n if mode == "images" else None
    scenes, t = [], 0.0
    for i, b in enumerate(raw, 1):
        dur = equal_dur if equal_dur is not None else float(b["dur"])
        scenes.append({"n": i, "start": t, "end": t + dur, "dur": round(dur, 4),
                       "text": b.get("label", "")})
        t += dur

    return _validate_and_write(project_dir, scenes, t, n, total_from="beats.json")


def _validate_and_write(project_dir, scenes, total_dur, n, total_from="audio"):
    errs, warns = [], []
    if len(scenes) != n:
        errs.append(f"{len(scenes)} beats built, expected exactly {n}")
    for s in scenes:
        if s["dur"] < BEAT_MIN_SEC:
            errs.append(f"beat {s['n']} is {s['dur']:.2f}s, under the {BEAT_MIN_SEC}s floor")
        elif s["dur"] > BEAT_HARD_MAX_SEC:
            errs.append(f"beat {s['n']} is {s['dur']:.2f}s, over the {BEAT_HARD_MAX_SEC}s hard max")
        elif s["dur"] > BEAT_SOFT_MAX_SEC:
            warns.append(f"beat {s['n']} is {s['dur']:.2f}s, over the {BEAT_SOFT_MAX_SEC}s soft max")

    if total_dur < DURATION_MIN_SEC:
        warns.append(f"total {total_dur:.1f}s is under the {DURATION_MIN_SEC}s "
                     f"floor for a Short to stand alone")
    elif total_dur > DURATION_SOFT_MAX_SEC:
        warns.append(f"total {total_dur:.1f}s is over the {DURATION_SOFT_MAX_SEC}s "
                     f"soft max — retention tends to drop off past here")
    if total_dur > DURATION_HARD_MAX_SEC:
        errs.append(f"total {total_dur:.1f}s exceeds YouTube's {DURATION_HARD_MAX_SEC:.0f}s Shorts cap")

    for w in warns:
        print(f"WARN: {w}")
    if errs:
        for e in errs:
            print(f"FAIL: {e}")
        return 1

    out_dir = os.path.join(project_dir, "out")
    os.makedirs(out_dir, exist_ok=True)
    json.dump(scenes, open(os.path.join(out_dir, "scenes.json"), "w"), indent=2)

    durs = [s["dur"] for s in scenes]
    print(f"OK  {len(scenes)} beat(s), total {total_dur:.1f}s (source: {total_from})")
    print(f"    dur min {min(durs):.2f}s | mean {sum(durs)/len(durs):.2f}s | max {max(durs):.2f}s")
    print(f"    wrote {out_dir}/scenes.json")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["propose", "build", "beats"])
    ap.add_argument("project_dir")
    a = ap.parse_args()
    fn = {"propose": propose, "build": build, "beats": beats}[a.command]
    sys.exit(fn(a.project_dir))
