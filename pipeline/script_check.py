#!/usr/bin/env python3
"""
Validate a Short's narration script. narration == "full" projects only — a
"none" narration project skips this stage entirely and writes out/beats.json
by hand instead.

Three things are enforced, and all three are real:
  1. the word band (WORDS_MIN..WORDS_MAX, hard-failing outside the hard band —
     these bands are Short-length in this pipeline's config.py, ~60-220 words)
  2. narration safety - nothing the voice-over will stumble on (narration_lint)
  3. the script lands under TTS_CHAR_CAP — almost always one part for a Short

Usage:
    python3 script_check.py <script.txt> <project_dir> [--fix] [--strict]

--fix rewrites script.txt with the blocking narration fixes applied.
Writes <project_dir>/script.txt and <project_dir>/narration_part1.txt .. partN.txt
"""
import sys
import os
import math
import argparse

from config import (WORDS_MIN, WORDS_MAX, WORDS_HARD_MIN, WORDS_HARD_MAX,
                    TTS_CHAR_CAP, TTS_CHAR_TARGET)
import narration_lint


def fail(msg):
    print(f"FAIL: {msg}")
    sys.exit(1)


def split_into_parts(paras, cap):
    """Fewest parts that fit under cap, balanced evenly.

    Greedy-filling the first part to the cap leaves a stub second part, which
    sounds wrong: the halves pick up different room tone and the join is audible.
    """
    total = len("\n\n".join(paras))
    n = max(1, math.ceil(total / cap))
    while True:
        target = total / n
        parts, cur = [], []
        for p in paras:
            cur.append(p)
            if len("\n\n".join(cur)) >= target and len(parts) < n - 1:
                parts.append(cur)
                cur = []
        if cur:
            parts.append(cur)
        built = ["\n\n".join(p).strip() + "\n" for p in parts]
        if all(len(b) <= cap for b in built) or n >= len(paras):
            return built
        n += 1


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("script")
    ap.add_argument("project_dir")
    ap.add_argument("--fix", action="store_true",
                    help="apply the blocking narration fixes to the source script")
    ap.add_argument("--strict", action="store_true",
                    help="advisory narration issues (numerals, ALL CAPS) also fail")
    a = ap.parse_args()

    raw = open(a.script, encoding="utf-8").read()
    fixed, fixes = narration_lint.autofix(raw)

    print("Narration safety:")
    if fixes:
        if not a.fix:
            for f in fixes:
                print(f"  FAIL: {f}")
            fail("blocking narration issues. Re-run with --fix to apply them.")
        for f in fixes:
            print(f"  fixed: {f}")
        open(a.script, "w", encoding="utf-8").write(fixed)
        print(f"  rewrote {a.script}")
    else:
        print("  clean")

    if narration_lint.report(fixed, strict=a.strict) and a.strict:
        fail("advisory narration issues under --strict")

    text = fixed
    words = len(text.split())
    if not (WORDS_HARD_MIN <= words <= WORDS_HARD_MAX):
        fail(f"word count {words} outside hard band {WORDS_HARD_MIN}-{WORDS_HARD_MAX}")
    if not (WORDS_MIN <= words <= WORDS_MAX):
        print(f"\nWARN: word count {words} outside target {WORDS_MIN}-{WORDS_MAX} "
              f"(inside hard band, continuing)")

    paras = [p.strip() for p in text.strip().split("\n\n") if p.strip()]
    parts = split_into_parts(paras, TTS_CHAR_TARGET)
    for i, p in enumerate(parts, 1):
        if len(p) > TTS_CHAR_CAP:
            fail(f"part {i} is {len(p)} chars, over the {TTS_CHAR_CAP} cap")

    os.makedirs(a.project_dir, exist_ok=True)
    canon = os.path.join(a.project_dir, "script.txt")
    if os.path.abspath(canon) != os.path.abspath(a.script):
        open(canon, "w", encoding="utf-8").write(text)

    print("\nTTS parts:")
    for i, p in enumerate(parts, 1):
        dest = os.path.join(a.project_dir, f"narration_part{i}.txt")
        open(dest, "w", encoding="utf-8").write(p)
        print(f"  part{i}: {len(p.split()):>5} words  {len(p):>6} chars  -> {dest}")

    print(f"\nOK  {words} words, {len(parts)} part(s), all under {TTS_CHAR_CAP} chars")
    print("Generate every part with the SAME voice settings. A mismatch is audible at the join.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
