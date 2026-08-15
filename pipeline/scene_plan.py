#!/usr/bin/env python3
"""
Plan the beats — this pipeline's word for what the parent pipeline calls
"scenes". Renamed because narration == "none" shorts have no script to cut
on, and because the count here is fixed, not derived.

Every Short from this pipeline has exactly IMAGES_PER_SHORT (5) or
CLIPS_PER_SHORT (4) beats, read from project.json's asset_mode. That's a
deliberate simplification over the parent pipeline's sentence-novelty cutting
algorithm: a script's timing bends to fit the fixed count, but the count
itself never varies with how the script happens to be written.

Two branches, chosen by project.json's narration field:

  narration == "full"    (propose / build)
    propose   Reads out/words.json and out/audio_meta.json, splits the total
              duration into N even target windows (N = the fixed count for
              this asset_mode), and snaps each internal boundary to the
              nearest sentence end (or, failing that, the nearest word) near
              its target — so cuts land on the audio without landing
              mid-sentence. Writes a draft boundaries.json plus a readable
              beats_draft.txt.
    build     Reads boundaries.json (the draft, or your edit of it),
              validates it has exactly N boundaries, and writes
              out/scenes.json.

  narration == "none"    (beats)
    beats     Reads out/beats.json — a hand-written list of exactly N
              [{"label": "...", "dur": ...}, ...] entries. Which beat gets how
              much of the runtime is an editorial call with no audio to
              derive it from, so the agent states it directly. Validates the
              count and durations and writes out/scenes.json in the same
              shape as the narrated branch, so manifest.py and assemble.py
              don't care which branch produced it.

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
                    DURATION_SOFT_MAX_SEC, DURATION_HARD_MAX_SEC)

SENT_END = re.compile(r"[.!?]$")


def fixed_count(project_dir):
    proj = json.load(open(os.path.join(project_dir, "project.json")))
    mode = proj.get("asset_mode")
    if mode == "images":
        return IMAGES_PER_SHORT
    if mode == "clips":
        return CLIPS_PER_SHORT
    print(f"FAIL: project.json asset_mode is {mode!r}, must be 'images' or 'clips'")
    sys.exit(1)


# ---------------- narration == "full" branch ----------------

def load_words(project_dir):
    return json.load(open(os.path.join(project_dir, "out", "words.json")))


def sentence_ends(words):
    """Word indices (0-based) that end a sentence — the preferred cut points."""
    return {i for i, w in enumerate(words) if SENT_END.search(w["w"])}


def propose(project_dir):
    words = load_words(project_dir)
    meta = json.load(open(os.path.join(project_dir, "out", "audio_meta.json")))
    audio_dur = meta["duration_sec"]
    n = fixed_count(project_dir)
    if n > len(words):
        print(f"FAIL: {n} beats requested but the script is only {len(words)} words")
        return 1

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

    print(f"OK  proposed {len(starts)} beat(s) (fixed count for this asset_mode)")
    print(f"    wrote {bp}")
    print(f"    wrote {draft}   <- read this, adjust boundaries.json, then run build")
    return 0


def build(project_dir):
    words = load_words(project_dir)
    meta = json.load(open(os.path.join(project_dir, "out", "audio_meta.json")))
    n = fixed_count(project_dir)
    B = json.load(open(os.path.join(project_dir, "boundaries.json")))["boundaries"]

    if len(B) != n:
        print(f"FAIL: boundaries.json has {len(B)} entries, this project needs exactly {n}")
        return 1
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
    the fixed count for this asset_mode, each with its own stated length."""
    n = fixed_count(project_dir)
    beats_path = os.path.join(project_dir, "out", "beats.json")
    if not os.path.exists(beats_path):
        print(f"FAIL: {beats_path} not found. Write it first, exactly {n} entries: "
              '[{"label": "arcade cabinet, 1988", "dur": 5.0}, ...]')
        return 1
    raw = json.load(open(beats_path))
    if len(raw) != n:
        print(f"FAIL: beats.json has {len(raw)} entries, this project needs exactly {n}")
        return 1

    scenes, t = [], 0.0
    for i, b in enumerate(raw, 1):
        dur = float(b["dur"])
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
