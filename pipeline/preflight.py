#!/usr/bin/env python3
"""
Run BEFORE anything else. Fails fast on the things that cannot be fixed mid-run.

Installs ffmpeg if it is missing. Checks the domain allowlist, which is fixed at
session start - discovering a blocked domain at scene 40 means the whole image
batch was wasted.

Usage:
    python3 preflight.py            # check, and install ffmpeg if needed
    python3 preflight.py --no-install
"""
import sys
import os
import subprocess
import shutil
import argparse
import glob

from config import REQUIRED_DOMAINS, FONT


def sh(cmd, timeout=600):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)


def install_ffmpeg():
    print("  ffmpeg missing - attempting install...")
    attempts = [
        "sudo -n apt-get update -qq && sudo -n apt-get install -y -qq ffmpeg",
        "apt-get update -qq && apt-get install -y -qq ffmpeg",
        "brew install ffmpeg",
        "sudo -n dnf install -y ffmpeg",
        "sudo -n pacman -S --noconfirm ffmpeg",
    ]
    for cmd in attempts:
        base = cmd.split()[0] if not cmd.startswith("sudo") else cmd.split()[2]
        if not shutil.which(base) and not shutil.which(cmd.split()[0]):
            continue
        print(f"    trying: {cmd.split('&&')[-1].strip()}")
        r = sh(cmd)
        if shutil.which("ffmpeg"):
            print("    installed")
            return True
        if r.stderr.strip():
            print(f"    failed: {r.stderr.strip().splitlines()[-1][:120]}")
    return False


def check_tool(name, allow_install=True):
    ok = shutil.which(name) is not None
    if not ok and name in ("ffmpeg", "ffprobe") and allow_install:
        ok = install_ffmpeg() and shutil.which(name) is not None
    print(f"  [{'OK' if ok else 'FAIL'}] {name}")
    return ok


def install_fonts():
    """Copy every font bundled in pipeline/fonts/ into the user font
    directory and refresh fontconfig's cache. This container is ephemeral,
    so a font installed by hand in one session (via fc-cache) is gone in the
    next - this is what makes FONT (config.py) durable across sessions
    without needing network access to fetch anything."""
    src_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")
    files = glob.glob(os.path.join(src_dir, "*.ttf")) + glob.glob(os.path.join(src_dir, "*.otf"))
    if not files:
        return
    dest_dir = os.path.expanduser("~/.fonts")
    os.makedirs(dest_dir, exist_ok=True)
    for f in files:
        shutil.copy(f, dest_dir)
    sh(f"fc-cache -f {dest_dir}")


def check_font(name):
    """fc-match always returns SOMETHING - a near-miss silently substitutes
    a fallback font instead of failing, so the check is whether the matched
    font's family aliases include the one asked for, not just that fc-match
    succeeded. A font can register multiple family names for the same file
    (e.g. Poppins Black reports both "Poppins" and "Poppins Black") -
    %{family} returns all of them comma-joined, so check membership, not
    equality against the first one."""
    r = subprocess.run(["fc-match", "--format=%{family}", name],
                       capture_output=True, text=True)
    aliases = [f.strip() for f in r.stdout.split(",")]
    ok = name in aliases
    note = "" if ok else f" (fell back to {aliases!r})"
    print(f"  [{'OK' if ok else 'FAIL'}] {name}{note}")
    return ok


def check_domain(d):
    """A real origin response (any status) proves reachability. A proxy block
    surfaces as a connection failure or an x-deny-reason header."""
    r = subprocess.run(["curl", "-s", "-o", "/dev/null", "-D", "-", "-m", "15",
                        f"https://{d}"], capture_output=True, text=True)
    hdrs = r.stdout.lower()
    blocked = "x-deny-reason" in hdrs
    reached = r.returncode == 0 and "http/" in hdrs
    ok = reached and not blocked
    note = "" if ok else (" (proxy blocked)" if blocked else " (unreachable)")
    print(f"  [{'OK' if ok else 'FAIL'}] {d}{note}")
    return ok


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--no-install", action="store_true")
    a = ap.parse_args()

    print("Tools:")
    tools = all(check_tool(t, allow_install=not a.no_install)
                for t in ["ffmpeg", "ffprobe", "curl", "python3"])

    print("Domains (must be allowlisted at session start):")
    doms = all(check_domain(d) for d in REQUIRED_DOMAINS)

    print("Fonts:")
    if not a.no_install:
        install_fonts()
    fonts = check_font(FONT)

    if not (tools and doms and fonts):
        print("\nPREFLIGHT FAILED - fix before starting. The domain allowlist cannot "
              "be changed mid-session; restart the session with all domains enabled.")
        return 1
    print("\nPREFLIGHT OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
