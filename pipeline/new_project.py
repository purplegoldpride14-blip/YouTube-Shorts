#!/usr/bin/env python3
"""
Scaffold a project folder, or update an existing project's metadata.

Usage:
    python3 new_project.py <slug> --asset-mode images|clips --narration full|none
                            [--audio music|none]
                            [--niche "..."] [--topic "..."] [--title "..."] [--no-hashtags]

Creates ../projects/<slug>/ with audio/ srt/ frames/ out/ and a project.json that
carries the niche, topic, title, asset_mode, narration and audio choice forward
through every later stage. Safe to re-run on an existing slug: any flag you
pass overwrites that field in project.json, everything else is left as-is.

--audio only applies to narration == "none" projects (a "full" project's
audio is always its narration track, so this flag is ignored there). Pick
"music" for the beat count's usual music-bed treatment (drop a file in
audio/music.* before assemble.py), or "none" for a silent video with no
audio track at all. assemble.py refuses to run for a narration == "none"
project until this is set.

niche defaults to nothing in particular — this pipeline is built around
nostalgia content but isn't locked to it; the niche stage (playbook 01)
presents nostalgia as the likely answer and leaves the door open to anything
else. topic is the specific angle within that niche — a decade, a city, a
subculture, a trend.

asset_mode and narration are independent choices — all four combinations are
valid (e.g. a "clips" short with "none" narration is a pure POV-nostalgia clip
over music; an "images" short with "full" narration is closer to a mini
Icons-Illustrated-style piece).
"""
import os
import json
import argparse
from datetime import date

from config import VALID_ASSET_MODES, VALID_NARRATION, VALID_AUDIO


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("slug")
    ap.add_argument("--asset-mode", choices=VALID_ASSET_MODES, default=None)
    ap.add_argument("--narration", choices=VALID_NARRATION, default=None)
    ap.add_argument("--audio", choices=VALID_AUDIO, default=None,
                    help="narration == none only: 'music' (bed under the visuals) or 'none' (silent)")
    ap.add_argument("--niche", default=None, help="e.g. 'nostalgia' (the likely default), or anything else")
    ap.add_argument("--topic", default=None, help="the specific angle — a decade, city, subculture, trend")
    ap.add_argument("--title", default=None)
    ap.add_argument("--no-hashtags", action="store_true", default=None,
                    help="disable hashtags in the description for this project (on by default for Shorts)")
    ap.add_argument("--root", default=os.path.join(os.path.dirname(__file__), "..", "projects"))
    a = ap.parse_args()

    root = os.path.abspath(os.path.join(a.root, a.slug))
    for sub in ("audio", "srt", "frames", "out"):
        os.makedirs(os.path.join(root, sub), exist_ok=True)

    p = os.path.join(root, "project.json")
    if os.path.exists(p):
        meta = json.load(open(p))
    else:
        meta = {
            "slug": a.slug,
            "created": str(date.today()),
            "asset_mode": None,
            "narration": None,
            "audio": None,
            "niche": "",
            "topic": "",
            "title": "",
            "no_hashtags": False,
            "style_locked": False,
            "notes": "",
        }
    if a.asset_mode is not None:
        meta["asset_mode"] = a.asset_mode
    if a.narration is not None:
        meta["narration"] = a.narration
    if a.audio is not None:
        meta["audio"] = a.audio
    if a.niche is not None:
        meta["niche"] = a.niche
    if a.topic is not None:
        meta["topic"] = a.topic
    if a.title is not None:
        meta["title"] = a.title
    if a.no_hashtags is not None:
        meta["no_hashtags"] = a.no_hashtags
    meta.setdefault("title", "")
    json.dump(meta, open(p, "w"), indent=2)

    style = os.path.join(root, "style.json")
    if not os.path.exists(style):
        json.dump({"style_block": "", "characters": {}, "reference_notes": ""},
                  open(style, "w"), indent=2)

    print(f"OK  {root}")
    for f in ("project.json", "style.json", "audio/", "srt/", "frames/", "out/"):
        print(f"    {f}")

    if not meta["asset_mode"] or not meta["narration"]:
        print("\nWARN: asset_mode and/or narration not set yet — set both before scene planning.")
    if meta["narration"] == "none" and not meta.get("audio"):
        print("\nWARN: audio not set yet — set --audio music|none before assemble.py will run.")

    print("\nNext:")
    if meta["narration"] == "full":
        print(f"    write the script, then script_check.py <script.txt> {root} --fix")
    else:
        print(f"    write out/beats.json directly (no script stage for narration=none)")
        if meta.get("audio") == "music":
            print(f"    and drop a music bed into {root}/audio/music.<ext>")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

