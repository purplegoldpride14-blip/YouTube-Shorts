#!/usr/bin/env python3
"""
Merge the narration parts, raise the volume, and emit exact offsets for the SRT.

Three things happen here, in this order:

  1. PART ORDER is verified against the script, not trusted from the filename.
     Each candidate ordering is scored by how consistent its characters-per-second
     is across parts. The correct order is obvious once you measure it; the
     filename is not evidence.

  2. OFFSETS come from decoded sample counts, never nominal mp3 duration. The
     container duration and the decoded duration differ by tens of milliseconds
     because of encoder delay and padding, and that difference drifts every
     caption in every later part.

  3. VOLUME is raised to TARGET_LUFS with a two-pass linear loudnorm applied to
     the merged track. One gain for the whole track means no level jump at the
     join, and linear mode is sample-count preserving, so the offsets survive.

Usage:
    python3 audio_merge.py <audio_dir> <project_dir> [--no-boost]

audio_dir: the voice-over files, any names, any of mp3/wav/m4a/flac/aac/ogg.
Writes <project_dir>/out/merged.wav and <project_dir>/out/audio_meta.json
"""
import sys
import os
import json
import glob
import re
import subprocess
import itertools
import argparse

from config import WAV_RATE, WAV_CHANNELS, TARGET_LUFS, TARGET_TP, TARGET_LRA

AUDIO_EXTS = ("mp3", "wav", "m4a", "flac", "aac", "ogg", "opus")


def run(cmd, check=True):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if check and r.returncode != 0:
        print("FAIL:", " ".join(cmd[:14]), "...")
        print(r.stderr[-3000:])
        sys.exit(1)
    return r


def probe(path, entry):
    return run(["ffprobe", "-v", "error", "-select_streams", "a:0",
                "-show_entries", entry, "-of", "csv=p=0", path]).stdout.strip()


def samples(path):
    return int(probe(path, "stream=duration_ts"))


def duration(path):
    return float(probe(path, "format=duration").split(",")[0])


def find_audio(audio_dir):
    files = []
    for e in AUDIO_EXTS:
        files += glob.glob(os.path.join(audio_dir, f"*.{e}"))
    return sorted(f for f in files if not os.path.basename(f).startswith("_"))


def order_by_speech_rate(files, part_texts):
    """Pick the assignment of files to script parts with the most consistent
    characters-per-second. Returns (ordered_files, report_lines)."""
    n = len(files)
    if n != len(part_texts):
        return files, [f"WARN: {n} audio file(s) but {len(part_texts)} script part(s); "
                       f"falling back to filename order"]
    if n == 1:
        return files, ["  single part, nothing to disambiguate"]

    durs = {f: duration(f) for f in files}
    chars = [len(t) for t in part_texts]

    best, best_spread = None, None
    for perm in itertools.permutations(files):
        rates = [chars[i] / durs[f] for i, f in enumerate(perm)]
        spread = max(rates) - min(rates)
        if best_spread is None or spread < best_spread:
            best, best_spread = perm, spread

    lines = []
    natural = sorted(files, key=lambda f: [int(x) if x.isdigit() else x
                                           for x in re.split(r"(\d+)", os.path.basename(f))])
    rates = [chars[i] / durs[f] for i, f in enumerate(best)]
    for i, f in enumerate(best):
        lines.append(f"  part{i+1}: {os.path.basename(f):<28} "
                     f"{durs[f]:8.2f}s  {rates[i]:5.2f} chars/sec")
    lines.append(f"  spread {best_spread:.2f} chars/sec across parts")
    if list(best) != natural:
        lines.append("  NOTE: measured order differs from filename order. "
                     "Measured order wins; confirm against the transcript once the SRT exists.")
    if best_spread > 3.0:
        lines.append("  WARN: parts were read at noticeably different speeds. "
                     "Check that every part used the same voice settings.")
    return list(best), lines


def measure_loudness(path):
    r = run(["ffmpeg", "-v", "info", "-i", path, "-af",
             f"loudnorm=I={TARGET_LUFS}:TP={TARGET_TP}:LRA={TARGET_LRA}:print_format=json",
             "-f", "null", "-"])
    m = re.search(r"\{[^{}]*\"input_i\"[\s\S]*?\}", r.stderr)
    if not m:
        print("FAIL: could not measure loudness")
        sys.exit(1)
    return json.loads(m.group(0))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("audio_dir")
    ap.add_argument("project_dir")
    ap.add_argument("--no-boost", action="store_true",
                    help="merge without raising the volume")
    a = ap.parse_args()

    out_dir = os.path.join(a.project_dir, "out")
    os.makedirs(out_dir, exist_ok=True)

    files = find_audio(a.audio_dir)
    if not files:
        print(f"FAIL: no audio files in {a.audio_dir}")
        return 1

    part_texts = []
    for p in sorted(glob.glob(os.path.join(a.project_dir, "narration_part*.txt")),
                    key=lambda p: int(re.search(r"(\d+)", os.path.basename(p)).group(1))):
        part_texts.append(open(p, encoding="utf-8").read())

    print(f"Part order ({len(files)} file(s), verified by speech rate):")
    files, lines = order_by_speech_rate(files, part_texts)
    for l in lines:
        print(l)

    print(f"\nDecoding to WAV at {WAV_RATE}Hz mono...")
    wavs = []
    for i, src in enumerate(files, 1):
        dst = os.path.join(out_dir, f"_part{i}.wav")
        run(["ffmpeg", "-v", "error", "-y", "-i", src, "-c:a", "pcm_s16le",
             "-ar", str(WAV_RATE), "-ac", str(WAV_CHANNELS), dst])
        wavs.append(dst)

    counts = [samples(w) for w in wavs]
    offsets, total = [], 0
    for c in counts:
        offsets.append(total / WAV_RATE)
        total += c

    listfile = os.path.join(out_dir, "_concat.txt")
    with open(listfile, "w") as f:
        for w in wavs:
            f.write(f"file '{os.path.abspath(w)}'\n")
    raw = os.path.join(out_dir, "_merged_raw.wav")
    run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0",
         "-i", listfile, "-c", "copy", raw])

    got = samples(raw)
    if got != total:
        print(f"FAIL: merged sample count {got} != expected {total}")
        return 1

    merged = os.path.join(out_dir, "merged.wav")
    boost = None
    if a.no_boost:
        os.replace(raw, merged)
    else:
        print(f"\nRaising volume to {TARGET_LUFS} LUFS (two-pass, linear)...")
        m = measure_loudness(raw)
        run(["ffmpeg", "-v", "error", "-y", "-i", raw, "-af",
             f"loudnorm=I={TARGET_LUFS}:TP={TARGET_TP}:LRA={TARGET_LRA}"
             f":measured_I={m['input_i']}:measured_TP={m['input_tp']}"
             f":measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}"
             f":offset={m['target_offset']}:linear=true:print_format=summary",
             "-ar", str(WAV_RATE), "-ac", str(WAV_CHANNELS),
             "-c:a", "pcm_s16le", merged])
        after = measure_loudness(merged)
        boost = {
            "input_lufs": float(m["input_i"]),
            "output_lufs": float(after["input_i"]),
            "gain_db": round(float(after["input_i"]) - float(m["input_i"]), 2),
            "target_lufs": TARGET_LUFS,
            "true_peak_db": float(after["input_tp"]),
        }
        print(f"  {boost['input_lufs']:.1f} LUFS -> {boost['output_lufs']:.1f} LUFS "
              f"({boost['gain_db']:+.1f} dB), true peak {boost['true_peak_db']:.1f} dB")
        if samples(merged) != total:
            print(f"WARN: loudnorm changed the sample count "
                  f"({samples(merged)} vs {total}); captions may drift. "
                  f"Re-run with --no-boost and normalise at assembly instead.")
        os.remove(raw)

    for w in wavs:
        os.remove(w)
    os.remove(listfile)

    meta = {
        "parts": [os.path.basename(p) for p in files],
        "sample_rate": WAV_RATE,
        "part_samples": counts,
        "part_offsets_sec": offsets,
        "total_samples": total,
        "duration_sec": total / WAV_RATE,
        "merged_wav": os.path.basename(merged),
        "loudness": boost,
    }
    json.dump(meta, open(os.path.join(out_dir, "audio_meta.json"), "w"), indent=2)

    print(f"\nSample-accurate merge verified: {got} == {total}")
    for i, (c, o) in enumerate(zip(counts, offsets), 1):
        print(f"  part{i}: {c:>10} samples  offset {o:12.7f}s")
    print(f"  TOTAL : {total:>10} samples  {total / WAV_RATE:.3f}s")
    print(f"  wrote {out_dir}/audio_meta.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
