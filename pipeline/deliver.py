#!/usr/bin/env python3
"""
Prepare the finished project for handoff.

Does four things, in order:
1. Verifies the deliverables exist: description.md, out/final.mp4, and — for
   narration == "full" projects only — narration_part*.txt and
   out/captions.srt. No thumbnail and no highlight-clip deliverables; this
   pipeline doesn't produce either.
2. Mirrors description.md and narration_part*.txt (if any) into out/, so
   out/ is the one folder with everything the user actually takes elsewhere.
   The originals at the project root are untouched.
3. Checks out/final.mp4 against GIT_PUSH_MAX_BYTES. Under the limit is left
   alone for the agent to git-add (with -f, since out/ is gitignored) and
   push. Over the limit is split into CHAT_CHUNK_BYTES pieces under
   out/chunks/, plus a sha256 of the original so the recipient can verify a
   reassembly.
4. Never touches git and never sends anything to chat - both are agent
   actions, not scripted ones.

Usage:
    python3 deliver.py <project_dir>
"""
import sys
import os
import json
import glob
import shutil
import hashlib

from config import GIT_PUSH_MAX_BYTES, CHAT_CHUNK_BYTES


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def split_file(src, dest_dir, chunk_bytes):
    os.makedirs(dest_dir, exist_ok=True)
    base = os.path.basename(src)
    for old in os.listdir(dest_dir):
        if old.startswith(base + ".part_"):
            os.remove(os.path.join(dest_dir, old))
    parts = []
    with open(src, "rb") as f:
        n = 0
        while True:
            data = f.read(chunk_bytes)
            if not data:
                break
            part_path = os.path.join(dest_dir, f"{base}.part_{n:03d}")
            with open(part_path, "wb") as out:
                out.write(data)
            parts.append(part_path)
            n += 1
    return parts


def deliver_binary(path, chunks_dir):
    """Under the limit: leave in place, git-addable as-is. Over: split for chat.
    Returns (status, extra) where status is "git" or "chat"."""
    size = os.path.getsize(path)
    if size <= GIT_PUSH_MAX_BYTES:
        return "git", size
    checksum = sha256_of(path)
    parts = split_file(path, chunks_dir, CHAT_CHUNK_BYTES)
    sha_path = os.path.join(chunks_dir, os.path.basename(path) + ".sha256")
    with open(sha_path, "w") as f:
        f.write(f"{checksum}  {os.path.basename(path)}\n")
    return "chat", (checksum, parts)


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    pd = sys.argv[1]

    proj = json.load(open(os.path.join(pd, "project.json")))
    narrated = proj.get("narration") == "full"

    narration_files = sorted(glob.glob(os.path.join(pd, "narration_part*.txt")))
    required = {
        "description": os.path.join(pd, "description.md"),
        "video": os.path.join(pd, "out", "final.mp4"),
    }
    if narrated:
        required["captions"] = os.path.join(pd, "out", "captions.srt")
    missing = [name for name, p in required.items() if not os.path.exists(p)]
    if narrated and not narration_files:
        missing.append("narration")
    if missing:
        print(f"FAIL: missing deliverable(s) before running deliver.py: {', '.join(missing)}")
        for name in missing:
            if name in required:
                print(f"      expected {required[name]}")
            else:
                print(f"      expected {os.path.join(pd, 'narration_part*.txt')}")
        return 1

    have = ["description.md", "out/final.mp4"]
    if narrated:
        have += [f"{len(narration_files)} narration file(s)", "out/captions.srt"]
    print(f"OK  {', '.join(have)} present")

    out_dir = os.path.join(pd, "out")
    shutil.copy2(required["description"], os.path.join(out_dir, "description.md"))
    for f in narration_files:
        shutil.copy2(f, os.path.join(out_dir, os.path.basename(f)))
    if narration_files:
        print(f"OK  mirrored description.md and narration into {out_dir}")
    else:
        print(f"OK  mirrored description.md into {out_dir}")

    git_paths, chat_items = [], []

    status, extra = deliver_binary(required["video"], os.path.join(out_dir, "chunks"))
    if status == "git":
        print(f"OK  out/final.mp4: {extra:,} bytes, under the git push limit")
        git_paths.append("out/final.mp4")
    else:
        checksum, parts = extra
        print(f"OK  out/final.mp4 over the git push limit - split into "
              f"{len(parts)} part(s), sha256 {checksum}")
        chat_items.append(("out/final.mp4", checksum, parts))

    always = ["description.md", "out/description.md"]
    if narrated:
        always.append("out/captions.srt")
    always += [os.path.join("out", os.path.basename(f)) for f in narration_files]
    git_paths = always + git_paths

    print(f"\nNEXT: git add -f {' '.join(git_paths)}, commit, push")
    if chat_items:
        for rel, checksum, parts in chat_items:
            print(f"      then send the {len(parts)} chunk file(s) for {rel} via chat, "
                  f"with sha256 {checksum}")
        print("      reassembly: cat <name>.part_* > <name>, or Windows copy /b")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
