#!/usr/bin/env python3
"""
Resumable asset-batch bookkeeping — images or clips, whichever project.json's
asset_mode says.

The agent drives OpenArt through MCP tool calls, because a shell script cannot
call MCP. What it must NOT do is hold the batch state in context. Every
submission and every download is recorded here, so a run that dies at beat 15
resumes at beat 15 instead of spending credits regenerating fifteen assets.

Agent loop, no approval gates between beats:
    manifest.py init   <project_dir>
    manifest.py next   <project_dir> [count]     -> beats still needing a submit
    manifest.py submit <project_dir> <n> <historyId>
    manifest.py record <project_dir> <n> <url>
    manifest.py fetch  <project_dir>             -> downloads everything recorded
    manifest.py verify <project_dir>             -> checks the files are real
    manifest.py retry  <project_dir> <n> [...]   -> puts beats back to todo
    manifest.py status <project_dir>

Reads out/scenes.json, prompts.json and project.json; writes out/manifest.json.
asset_mode == "images"  -> frames/beat_NNN.png, floor MIN_IMAGE_BYTES
asset_mode == "clips"   -> frames/beat_NNN.mp4, floor MIN_VIDEO_BYTES
"""
import sys
import os
import json
import subprocess
from collections import Counter

from config import MIN_IMAGE_BYTES, MIN_VIDEO_BYTES


def asset_kind(project_dir):
    meta = json.load(open(os.path.join(project_dir, "project.json")))
    mode = meta.get("asset_mode")
    if mode not in ("images", "clips"):
        print(f"FAIL: project.json asset_mode is {mode!r}, must be 'images' or 'clips'")
        sys.exit(1)
    ext = "png" if mode == "images" else "mp4"
    floor = MIN_IMAGE_BYTES if mode == "images" else MIN_VIDEO_BYTES
    return mode, ext, floor


def paths(project_dir):
    out = os.path.join(project_dir, "out")
    return {
        "scenes": os.path.join(out, "scenes.json"),
        "prompts": os.path.join(project_dir, "prompts.json"),
        "manifest": os.path.join(out, "manifest.json"),
        "frames": os.path.join(project_dir, "frames"),
    }


def load(p):
    return json.load(open(p))


def save(p, d):
    json.dump(d, open(p, "w"), indent=2)


def cmd_init(pd):
    P = paths(pd)
    mode, ext, _ = asset_kind(pd)
    scenes, prompts = load(P["scenes"]), load(P["prompts"])
    missing = [str(s["n"]) for s in scenes if str(s["n"]) not in prompts]
    if missing:
        print(f"FAIL: no prompt for beat(s) {', '.join(missing[:20])}")
        return 1
    m = {"asset_mode": mode, "ext": ext, "beats": {}}
    for s in scenes:
        n = str(s["n"])
        m["beats"][n] = {"n": s["n"], "prompt": prompts[n], "state": "todo",
                         "historyId": None, "url": None, "file": None}
    save(P["manifest"], m)
    print(f"OK  initialised {len(m['beats'])} beat(s) [{mode}] -> {P['manifest']}")
    return 0


def cmd_next(pd, count=1):
    m = load(paths(pd)["manifest"])
    todo = sorted((v for v in m["beats"].values() if v["state"] == "todo"),
                  key=lambda v: v["n"])
    for v in todo[:int(count)]:
        print(json.dumps({"n": v["n"], "prompt": v["prompt"]}))
    return 0


def _set(pd, n, **kw):
    P = paths(pd)
    m = load(P["manifest"])
    if str(n) not in m["beats"]:
        print(f"FAIL: no beat {n}")
        return None, None
    m["beats"][str(n)].update(**kw)
    save(P["manifest"], m)
    return m, P


def cmd_submit(pd, n, hid):
    m, _ = _set(pd, n, state="submitted", historyId=hid)
    if m:
        print(f"OK  beat {n} submitted ({hid})")
    return 0 if m else 1


def cmd_record(pd, n, url):
    m, _ = _set(pd, n, state="ready", url=url)
    if m:
        print(f"OK  beat {n} url recorded")
    return 0 if m else 1


def cmd_retry(pd, *ns):
    for n in ns:
        _set(pd, n, state="todo", historyId=None, url=None, file=None)
    print(f"OK  reset {len(ns)} beat(s) to todo")
    return 0


def cmd_fetch(pd):
    P = paths(pd)
    mode, ext, floor = asset_kind(pd)
    m = load(P["manifest"])
    os.makedirs(P["frames"], exist_ok=True)
    got = failed = 0
    for k in sorted(m["beats"], key=int):
        v = m["beats"][k]
        if v["state"] != "ready" or not v["url"]:
            continue
        dest = os.path.join(P["frames"], f"beat_{v['n']:03d}.{ext}")
        r = subprocess.run(["curl", "-s", "-L", "-o", dest, v["url"]])
        ok = (r.returncode == 0 and os.path.exists(dest)
              and os.path.getsize(dest) > floor)
        if ok:
            v.update(state="done", file=os.path.abspath(dest))
            got += 1
        else:
            failed += 1
            print(f"WARN: beat {v['n']} download failed")
    save(P["manifest"], m)
    print(f"OK  downloaded {got}, failed {failed} [{mode}]")
    return 0


def cmd_verify(pd):
    P = paths(pd)
    mode, ext, floor = asset_kind(pd)
    m = load(P["manifest"])
    bad = []
    for k in sorted(m["beats"], key=int):
        v = m["beats"][k]
        f = v.get("file") or os.path.join(P["frames"], f"beat_{v['n']:03d}.{ext}")
        if os.path.exists(f) and os.path.getsize(f) > floor:
            if v["state"] != "done":
                v.update(state="done", file=os.path.abspath(f))
            continue
        bad.append(v["n"])
        if v["state"] == "done":
            v.update(state="ready", file=None)
    save(P["manifest"], m)
    if bad:
        print(f"WARN: {len(bad)} beat asset(s) missing or truncated: {bad[:20]}")
        print("      fetch again, or retry those beats")
        return 1
    print(f"OK  all {len(m['beats'])} {mode} asset(s) present and non-trivial")
    return 0


def cmd_status(pd):
    m = load(paths(pd)["manifest"])
    c = Counter(v["state"] for v in m["beats"].values())
    total = len(m["beats"])
    print(f"[{m.get('asset_mode', '?')}] total {total} | "
          + " | ".join(f"{k} {v}" for k, v in sorted(c.items())))
    missing = [v["n"] for v in sorted(m["beats"].values(), key=lambda x: x["n"])
               if v["state"] != "done"]
    if missing:
        head = ", ".join(map(str, missing[:20]))
        print(f"not done ({len(missing)}): {head}{' ...' if len(missing) > 20 else ''}")
        return 0
    print("ALL BEATS DONE - ready to assemble")
    return 0


COMMANDS = {
    "init": lambda a: cmd_init(a[0]),
    "next": lambda a: cmd_next(a[0], a[1] if len(a) > 1 else 1),
    "submit": lambda a: cmd_submit(a[0], a[1], a[2]),
    "record": lambda a: cmd_record(a[0], a[1], a[2]),
    "retry": lambda a: cmd_retry(a[0], *a[1:]),
    "fetch": lambda a: cmd_fetch(a[0]),
    "verify": lambda a: cmd_verify(a[0]),
    "status": lambda a: cmd_status(a[0]),
}

if __name__ == "__main__":
    if len(sys.argv) < 3 or sys.argv[1] not in COMMANDS:
        print(__doc__)
        sys.exit(2)
    sys.exit(COMMANDS[sys.argv[1]](sys.argv[2:]) or 0)
