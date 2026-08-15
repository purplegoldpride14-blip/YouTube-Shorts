#!/usr/bin/env python3
"""
Build captions.srt by aligning the Descript SRT back onto the written script.

The raw SRT is a transcript of the audio, so it carries three problems: ASR
errors on proper nouns, filler the model inserted, and anything Descript picked
up that was never in the script. Rather than hand-fixing those, this aligns the
transcript word stream against the script word stream and keeps the SCRIPT's
words with the TRANSCRIPT's timings:

  - words in both              -> script spelling, ASR timing
  - ASR heard something else   -> script spelling, ASR timing span
  - ASR heard extra words      -> dropped (nothing survives that is not in the script)
  - ASR missed script words    -> restored, timed by interpolation

Then it offsets each part by the exact sample-derived offset, regroups the words
into cues of at most SRT_MAX_WORDS_PER_CUE, breaking at sentence ends and
balancing chunks so no cue is left orphaned, and validates the result.

Usage:
    python3 srt_build.py <srt_dir> <project_dir>

srt_dir must contain part1_raw.srt .. partN_raw.srt
Writes <project_dir>/out/captions.srt and <project_dir>/out/words.json
"""
import sys
import os
import re
import json
import glob
import math
import difflib
import argparse

from config import SRT_MAX_WORDS_PER_CUE

SENT_END = re.compile(r"[.!?]$")


def ts2s(t):
    h, m, rest = t.split(":")
    s, ms = rest.replace(".", ",").split(",")
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000


def s2ts(x):
    x = max(0.0, x)
    ms = int(round(x * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def parse_srt(path, offset=0.0):
    cues = []
    raw = open(path, encoding="utf-8-sig").read().strip()
    for block in re.split(r"\n\s*\n", raw):
        lines = [l for l in block.split("\n") if l.strip()]
        if len(lines) < 2:
            continue
        tl = next((l for l in lines if "-->" in l), None)
        if not tl:
            continue
        a, b = [x.strip() for x in tl.split("-->")]
        text = " ".join(" ".join(lines[lines.index(tl) + 1:]).split())
        if not text:
            continue
        cues.append((ts2s(a) + offset, ts2s(b) + offset, text))
    return cues


def cues_to_words(cues):
    """Spread each cue's duration across its words by character share."""
    out = []
    for st, en, text in cues:
        ws = text.split()
        if not ws:
            continue
        total = sum(len(w) for w in ws)
        t = st
        span = max(en - st, 0.001)
        for i, w in enumerate(ws):
            end = en if i == len(ws) - 1 else t + span * (len(w) / total)
            out.append([w, t, max(end, t + 0.01)])
            t = end
    return out


def norm(w):
    return re.sub(r"[^a-z0-9]", "", w.lower())


def align(asr_words, script_words):
    """Return script words carrying ASR timings, plus a stats dict."""
    a_norm = [norm(w[0]) for w in asr_words]
    s_norm = [norm(w) for w in script_words]

    sm = difflib.SequenceMatcher(None, a_norm, s_norm, autojunk=False)
    out = []
    stats = {"matched": 0, "corrected": 0, "dropped": 0, "restored": 0}

    def asr_span(i1, i2, fallback_t):
        if i2 > i1:
            return asr_words[i1][1], asr_words[i2 - 1][2]
        t = asr_words[i1][1] if i1 < len(asr_words) else fallback_t
        return t, t

    cursor = 0.0
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                w = script_words[j1 + k]
                _, st, en = asr_words[i1 + k]
                out.append([w, st, en])
                cursor = en
            stats["matched"] += i2 - i1
            continue

        if tag == "delete":
            stats["dropped"] += i2 - i1
            continue

        # replace / insert: lay the script words across whatever time the ASR used
        chunk = script_words[j1:j2]
        if not chunk:
            continue
        st, en = asr_span(i1, i2, cursor)
        st = max(st, cursor)
        if en <= st:
            en = st + 0.16 * len(chunk)  # nothing to borrow; monotonicity fixes it later
        total = sum(max(len(w), 1) for w in chunk)
        t = st
        for k, w in enumerate(chunk):
            e = en if k == len(chunk) - 1 else t + (en - st) * (max(len(w), 1) / total)
            out.append([w, t, max(e, t + 0.02)])
            t = max(e, t + 0.02)
        cursor = t
        if tag == "replace":
            stats["corrected"] += len(chunk)
            stats["dropped"] += (i2 - i1)
        else:
            stats["restored"] += len(chunk)

    return out, stats


def group_cues(words, maxw):
    """Sentence-aware grouping. Each sentence is split into balanced chunks so a
    sentence of six words becomes 3+3, never 5+1."""
    cues, sent = [], []
    for w in words:
        sent.append(w)
        if SENT_END.search(w[0]):
            cues += _chunk(sent, maxw)
            sent = []
    if sent:
        cues += _chunk(sent, maxw)
    return cues


def _chunk(sent, maxw):
    n = max(1, math.ceil(len(sent) / maxw))
    base, rem = divmod(len(sent), n)
    out, i = [], 0
    for k in range(n):
        size = base + (1 if k < rem else 0)
        part = sent[i:i + size]
        i += size
        if part:
            out.append([part[0][1], part[-1][2], " ".join(p[0] for p in part), len(part)])
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("srt_dir")
    ap.add_argument("project_dir")
    a = ap.parse_args()

    out_dir = os.path.join(a.project_dir, "out")
    meta = json.load(open(os.path.join(out_dir, "audio_meta.json")))
    offsets = meta["part_offsets_sec"]

    srts = sorted(glob.glob(os.path.join(a.srt_dir, "part*_raw.srt")),
                  key=lambda p: int(re.search(r"(\d+)", os.path.basename(p)).group(1)))
    scripts = sorted(glob.glob(os.path.join(a.project_dir, "narration_part*.txt")),
                     key=lambda p: int(re.search(r"(\d+)", os.path.basename(p)).group(1)))

    if len(srts) != len(offsets):
        print(f"FAIL: {len(srts)} raw SRT(s) but {len(offsets)} audio part(s)")
        return 1
    if len(scripts) != len(srts):
        print(f"FAIL: {len(scripts)} script part(s) but {len(srts)} raw SRT(s)")
        return 1

    all_words, prev_end = [], None
    totals = {"matched": 0, "corrected": 0, "dropped": 0, "restored": 0}

    for i, (srt, script, off) in enumerate(zip(srts, scripts, offsets), 1):
        cues = parse_srt(srt, off)
        if not cues:
            print(f"FAIL: {srt} has no cues")
            return 1
        asr = cues_to_words(cues)
        sw = open(script, encoding="utf-8").read().split()
        aligned, stats = align(asr, sw)

        for k in totals:
            totals[k] += stats[k]
        pct = 100.0 * stats["matched"] / max(len(sw), 1)
        print(f"  part{i}: {len(asr):>5} ASR words -> {len(aligned):>5} script words "
              f"| {pct:5.1f}% exact | corrected {stats['corrected']:>3} "
              f"| dropped {stats['dropped']:>3} | restored {stats['restored']:>3}")
        if pct < 85:
            print(f"    WARN: low match rate. Check that part{i}_raw.srt really is "
                  f"the transcript of narration_part{i}.txt.")

        if prev_end is not None:
            gap = aligned[0][1] - prev_end
            print(f"    seam {i-1}->{i}: gap {gap:+.3f}s "
                  f"[{'OVERLAP' if gap < 0 else 'ok'}]")
            if gap < -0.5:
                print("FAIL: seam overlap - the part offsets or the SRT order are wrong")
                return 1
        prev_end = aligned[-1][2]
        all_words += aligned

    # monotonicity
    fixed = 0
    for i in range(1, len(all_words)):
        if all_words[i][1] < all_words[i - 1][2]:
            all_words[i][1] = all_words[i - 1][2]
            fixed += 1
        if all_words[i][2] <= all_words[i][1]:
            all_words[i][2] = all_words[i][1] + 0.02
            fixed += 1

    dur = meta["duration_sec"]
    if all_words[-1][2] > dur:
        all_words[-1][2] = dur

    cues = group_cues(all_words, SRT_MAX_WORDS_PER_CUE)
    for i in range(1, len(cues)):
        if cues[i][0] < cues[i - 1][1]:
            cues[i][0] = cues[i - 1][1]
        if cues[i][1] <= cues[i][0]:
            cues[i][1] = cues[i][0] + 0.05

    srt_path = os.path.join(out_dir, "captions.srt")
    with open(srt_path, "w", encoding="utf-8") as f:
        for i, (st, en, tx, _) in enumerate(cues, 1):
            f.write(f"{i}\n{s2ts(st)} --> {s2ts(en)}\n{tx}\n\n")

    json.dump([{"w": w, "start": round(s, 3), "end": round(e, 3)}
               for w, s, e in all_words],
              open(os.path.join(out_dir, "words.json"), "w"), indent=1)

    over = [i for i, c in enumerate(cues, 1) if c[3] > SRT_MAX_WORDS_PER_CUE]
    if over:
        print(f"FAIL: {len(over)} cue(s) exceed {SRT_MAX_WORDS_PER_CUE} words")
        return 1

    tail = dur - cues[-1][1]
    print(f"\nOK  {len(all_words)} words -> {len(cues)} cues, "
          f"max {SRT_MAX_WORDS_PER_CUE} words each")
    print(f"    exact {totals['matched']} | corrected {totals['corrected']} | "
          f"dropped from ASR {totals['dropped']} | restored {totals['restored']}")
    print(f"    monotonicity fixes: {fixed}")
    print(f"    last cue ends {cues[-1][1]:.3f}s | audio {dur:.3f}s | trailing {tail:.3f}s")
    if tail < -0.001:
        print("FAIL: captions run past the end of the audio")
        return 1
    print(f"    wrote {srt_path}")
    print(f"    wrote {out_dir}/words.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
