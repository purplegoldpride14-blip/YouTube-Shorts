#!/usr/bin/env python3
"""
Validate a YouTube description against YouTube's real limit and the standing spec.

Checks:
  - character count <= DESCRIPTION_CHAR_CAP. This is YouTube's actual hard limit;
    past it YouTube truncates or refuses the paste. It is independent of, and
    stricter than, the word floor - a description can clear 500 words and still
    be nowhere near 5,000 characters.
  - word count >= DESCRIPTION_WORD_MIN (warning only)
  - no hashtags, unless the project turns that off

Usage:
    python3 description_check.py <description.md> [project.json]
"""
import sys
import os
import json

from config import (DESCRIPTION_CHAR_CAP, DESCRIPTION_WORD_MIN,
                    DESCRIPTION_NO_HASHTAGS)


def main(path, project=None):
    no_hash = DESCRIPTION_NO_HASHTAGS
    if project and os.path.exists(project):
        no_hash = json.load(open(project)).get("no_hashtags", no_hash)

    text = open(path, encoding="utf-8").read()
    chars, words = len(text), len(text.split())

    if chars > DESCRIPTION_CHAR_CAP:
        print(f"FAIL: {chars} characters exceeds YouTube's {DESCRIPTION_CHAR_CAP}-character "
              f"limit by {chars - DESCRIPTION_CHAR_CAP}. YouTube truncates or refuses "
              f"the paste past this point.")
        return 1

    if words < DESCRIPTION_WORD_MIN:
        print(f"WARN: {words} words is under the {DESCRIPTION_WORD_MIN}-word floor")

    if no_hash and "#" in text:
        print(f"FAIL: {text.count('#')} '#' character(s) found - this project's spec "
              f"says no hashtags")
        return 1

    print(f"OK  {words} words, {chars}/{DESCRIPTION_CHAR_CAP} characters "
          f"({DESCRIPTION_CHAR_CAP - chars} to spare)")
    return 0


if __name__ == "__main__":
    if len(sys.argv) not in (2, 3):
        print(__doc__)
        sys.exit(2)
    sys.exit(main(*sys.argv[1:]))
