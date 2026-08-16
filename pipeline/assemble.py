#!/usr/bin/env python3
"""
Assemble beats plus audio into the finished vertical Short.

Branches on project.json, not a flag, so a project can't drift from its own
declared mode partway through a run:

  asset_mode == "images"   Ken Burns (or static) stills, exactly like the
                            parent pipeline's long-form assembly, just at
                            Short-scale beat durations and native 9:16.
  asset_mode == "clips"    Each beat's OpenArt video clip is trimmed (if
                            longer than the beat) or looped (if shorter) to
                            fill its beat exactly, then concatenated. Clips
                            never get Ken Burns — they already have motion.
                            When VIDEO_AUDIO is True (Gemini Omni Flash's
                            native synchronized audio) and narration ==
                            "none", each clip's own generated audio
                            (dialogue etc.) is kept through trim/loop/concat
                            instead of stripped.

  narration == "full"      out/merged.wav is the track, out/captions.srt is
                            burned in as word-synced captions (same audio path
                            as the parent pipeline). asset_mode == "clips"
                            still strips each clip's own generated audio here
                            regardless of VIDEO_AUDIO, so it can't clash with
                            the read narration track.
  narration == "none"      no narration means no burned text of any kind -
                            beat labels are bookkeeping only, never rendered
                            into the video. Soundtrack source depends on
                            asset_mode:
                              images -> project.json's "audio" field alone:
                                "music" loops/trims audio/music.* to the
                                total beat duration at a bed level; "none"
                                is silent.
                              clips (VIDEO_AUDIO True) -> the clips' own
                                concatenated audio is always the primary
                                track; "audio" only decides whether
                                audio/music.* is ALSO mixed in underneath it,
                                ducked ("music") or not ("none").

Every beat is held for exactly its beat duration, so cuts land on the audio by
construction. The timeline is checked before a single frame is encoded.

Usage:
    python3 assemble.py <project_dir> [--motion none|kenburns] [--jobs N]
"""
import sys
import os
import re
import json
import glob
import subprocess
import tempfile
import argparse
from concurrent.futures import ThreadPoolExecutor

from config import (OUT_WIDTH, OUT_HEIGHT, OUT_FPS, VIDEO_CRF, VIDEO_PRESET,
                    TARGET_LUFS, TARGET_TP, TARGET_LRA, MOTION_DEFAULT,
                    KENBURNS_ZOOM, LOUDNESS_TOLERANCE, VIDEO_CLIP_SEC,
                    MUSIC_BED_LUFS, MUSIC_DUCK_LUFS, FONT, FONT_SIZE,
                    TEXT_SAFE_MARGIN_PX, VALID_AUDIO, VIDEO_AUDIO)

TS_RE = re.compile(r"(\d\d):(\d\d):(\d\d),(\d\d\d)")

ASS_HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font},{size},&H00FFFFFF,&H000000FF,&H00000000,&H96000000,1,0,0,0,100,100,0,0,1,3.5,0,2,70,70,{margin},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def run(cmd, check=True):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if check and r.returncode != 0:
        print("FAIL:", " ".join(cmd[:14]), "...")
        print(r.stderr[-3000:])
        sys.exit(1)
    return r


def frame_path(frames_dir, n, ext):
    return os.path.abspath(os.path.join(frames_dir, f"beat_{n:03d}.{ext}"))


def fmt_ass_ts(t):
    t = max(0.0, t)
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = int(t % 60)
    cs = int(round((t - int(t)) * 100))
    if cs == 100:
        cs = 0
        s += 1
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def parse_srt_ts(ts):
    h, m, s, ms = map(int, TS_RE.match(ts).groups())
    return h * 3600 + m * 60 + s + ms / 1000.0


def load_srt_cues(path):
    text = open(path, encoding="utf-8").read()
    cues = []
    for block in text.split("\n\n"):
        lines = block.strip().splitlines()
        if len(lines) < 2:
            continue
        m = re.search(r"(\d\d:\d\d:\d\d,\d\d\d)\s*-->\s*(\d\d:\d\d:\d\d,\d\d\d)", lines[1])
        if not m:
            continue
        cues.append((parse_srt_ts(m.group(1)), parse_srt_ts(m.group(2)), " ".join(lines[2:])))
    return cues


def write_ass_from_srt(srt_path, dest):
    cues = load_srt_cues(srt_path)
    header = ASS_HEADER.format(w=OUT_WIDTH, h=OUT_HEIGHT, font=FONT, size=FONT_SIZE,
                               margin=TEXT_SAFE_MARGIN_PX)
    events = [f"Dialogue: 0,{fmt_ass_ts(s)},{fmt_ass_ts(e)},Default,,0,0,0,,{t}"
             for s, e, t in cues]
    open(dest, "w", encoding="utf-8").write(header + "\n".join(events) + "\n")
    return len(events)


def measure_lufs(path):
    r = run(["ffmpeg", "-v", "info", "-i", path, "-af",
             f"loudnorm=I={TARGET_LUFS}:TP={TARGET_TP}:LRA={TARGET_LRA}:print_format=json",
             "-f", "null", "-"], check=False)
    m = re.search(r"\{[^{}]*\"input_i\"[\s\S]*?\}", r.stderr)
    return float(json.loads(m.group(0))["input_i"]) if m else None


def build_still_list(scenes, frames_dir):
    f = tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False)
    for s in scenes:
        f.write(f"file '{frame_path(frames_dir, s['n'], 'png')}'\nduration {s['dur']:.6f}\n")
    f.write(f"file '{frame_path(frames_dir, scenes[-1]['n'], 'png')}'\n")
    f.close()
    return f.name


def render_kenburns_segment(args):
    s, frames_dir, seg_dir = args
    dst = os.path.join(seg_dir, f"seg_{s['n']:04d}.mp4")
    frames = max(int(round(s["dur"] * OUT_FPS)), 1)
    step = (KENBURNS_ZOOM - 1.0) / frames
    if s["n"] % 2:
        z = f"min(zoom+{step:.6f},{KENBURNS_ZOOM})"
    else:
        z = f"if(eq(on,0),{KENBURNS_ZOOM},max(zoom-{step:.6f},1.0))"
    vf = (f"scale={OUT_WIDTH*2}:{OUT_HEIGHT*2}:force_original_aspect_ratio=decrease,"
          f"pad={OUT_WIDTH*2}:{OUT_HEIGHT*2}:(ow-iw)/2:(oh-ih)/2:color=black,"
          f"zoompan=z='{z}':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
          f":s={OUT_WIDTH}x{OUT_HEIGHT}:fps={OUT_FPS},format=yuv420p")
    run(["ffmpeg", "-v", "error", "-y", "-loop", "1", "-i", frame_path(frames_dir, s["n"], "png"),
         "-vf", vf, "-frames:v", str(frames), "-r", str(OUT_FPS),
         "-c:v", "libx264", "-crf", str(VIDEO_CRF), "-preset", VIDEO_PRESET, dst])
    return dst


def render_clip_segment(args):
    """Trim (clip longer than the beat) or loop (clip shorter than the beat) an
    OpenArt-generated clip to exactly fill its beat, scaled/cropped to output.
    keep_audio preserves the clip's own generated audio (dialogue etc.)
    through the trim/loop instead of stripping it - True only for
    narration == "none" clips projects with VIDEO_AUDIO set."""
    s, frames_dir, seg_dir, keep_audio = args
    src = frame_path(frames_dir, s["n"], "mp4")
    dst = os.path.join(seg_dir, f"seg_{s['n']:04d}.mp4")
    vf = (f"scale={OUT_WIDTH}:{OUT_HEIGHT}:force_original_aspect_ratio=increase,"
          f"crop={OUT_WIDTH}:{OUT_HEIGHT},format=yuv420p,fps={OUT_FPS}")
    audio_args = (["-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2"]
                  if keep_audio else ["-an"])
    if s["dur"] <= VIDEO_CLIP_SEC + 0.05:
        cmd = ["ffmpeg", "-v", "error", "-y", "-i", src, "-t", str(s["dur"]),
              "-vf", vf] + audio_args + ["-c:v", "libx264", "-crf", str(VIDEO_CRF),
              "-preset", VIDEO_PRESET, dst]
    else:
        cmd = ["ffmpeg", "-v", "error", "-y", "-stream_loop", "-1", "-i", src,
              "-t", str(s["dur"]), "-vf", vf] + audio_args + ["-c:v", "libx264",
              "-crf", str(VIDEO_CRF), "-preset", VIDEO_PRESET, dst]
    run(cmd)
    return dst


def prep_music_bed(project_dir, total_dur, target_lufs=MUSIC_BED_LUFS):
    """narration == 'none': find audio/music.* by hand, loudnorm to
    target_lufs, and loop/trim it to the video's total duration.
    target_lufs defaults to a standalone bed level (MUSIC_BED_LUFS); pass
    MUSIC_DUCK_LUFS when it's being mixed in underneath a clip's own
    dialogue audio instead."""
    audio_dir = os.path.join(project_dir, "audio")
    candidates = sorted(glob.glob(os.path.join(audio_dir, "music.*")))
    if not candidates:
        print(f"FAIL: no audio/music.* found in {audio_dir} — narration=none needs a music bed")
        sys.exit(1)
    src = candidates[0]
    out_dir = os.path.join(project_dir, "out")
    dst = os.path.join(out_dir, "music_bed.wav")
    filt = f"loudnorm=I={target_lufs}:TP={TARGET_TP}:LRA={TARGET_LRA}"
    run(["ffmpeg", "-v", "error", "-y", "-stream_loop", "-1", "-i", src,
         "-t", str(total_dur), "-af", filt, "-ar", "44100", "-ac", "2", dst])
    return dst


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("project_dir")
    ap.add_argument("--motion", choices=["none", "kenburns"], default=None,
                    help="asset_mode == images only; default from config.py")
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("-o", "--out", default=None)
    a = ap.parse_args()

    proj = json.load(open(os.path.join(a.project_dir, "project.json")))
    asset_mode, narration = proj.get("asset_mode"), proj.get("narration")
    if asset_mode not in ("images", "clips"):
        print(f"FAIL: project.json asset_mode is {asset_mode!r}")
        return 1
    if narration not in ("full", "none"):
        print(f"FAIL: project.json narration is {narration!r}")
        return 1

    motion = a.motion or (MOTION_DEFAULT if asset_mode == "images" else "none")

    out_dir = os.path.join(a.project_dir, "out")
    frames_dir = os.path.join(a.project_dir, "frames")
    scenes = json.load(open(os.path.join(out_dir, "scenes.json")))
    out_path = a.out or os.path.join(out_dir, "final.mp4")
    ext = "png" if asset_mode == "images" else "mp4"

    missing = [s["n"] for s in scenes if not os.path.exists(frame_path(frames_dir, s["n"], ext))]
    if missing:
        print(f"FAIL: {len(missing)} beat asset(s) missing: {missing[:20]}")
        return 1

    total = sum(s["dur"] for s in scenes)

    # ---- audio + captions ----
    # narration == "full" is the only mode with anything to burn as text —
    # narration == "none" means no voice-over AND no text of any kind, silent
    # or scored purely by project.json's audio field (asset_mode == "images")
    # or the clips' own generated audio (asset_mode == "clips", VIDEO_AUDIO).
    burn = None
    clip_native_audio = False   # True: concatenated clip audio is the primary track
    music_wav = None            # optional bed, mixed under clip_native_audio or standalone
    if narration == "full":
        meta = json.load(open(os.path.join(out_dir, "audio_meta.json")))
        wav = os.path.join(out_dir, meta["merged_wav"])
        if not os.path.exists(wav):
            print(f"FAIL: {wav} not found. Re-run audio_merge.py.")
            return 1
        drift = abs(total - meta["duration_sec"])
        if drift > 0.05:
            print(f"FAIL: beat durations total {total:.3f}s vs audio {meta['duration_sec']:.3f}s")
            return 1
        ass_path = os.path.join(out_dir, "burned_captions.ass")
        n_cues = write_ass_from_srt(os.path.join(out_dir, "captions.srt"), ass_path)
        ass_escaped = ass_path.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
        burn = f"ass='{ass_escaped}'"
        has_audio = True
        audio_dur = meta["duration_sec"]
        lufs = measure_lufs(wav)
        if lufs is not None:
            off = abs(lufs - TARGET_LUFS)
            print(f"Audio level: {lufs:.1f} LUFS (target {TARGET_LUFS})")
            if off > LOUDNESS_TOLERANCE:
                print(f"WARN: {off:.1f} dB from target. Re-run audio_merge.py.")
    else:
        audio_choice = proj.get("audio")
        if audio_choice not in VALID_AUDIO:
            print(f"FAIL: project.json audio is {audio_choice!r}, must be 'music' or 'none' "
                  f"(set with new_project.py --audio music|none)")
            return 1
        if asset_mode == "clips" and VIDEO_AUDIO:
            clip_native_audio = True
            has_audio = True
            wav = None
            if audio_choice == "music":
                music_wav = prep_music_bed(a.project_dir, total, target_lufs=MUSIC_DUCK_LUFS)
        elif audio_choice == "music":
            wav = prep_music_bed(a.project_dir, total)
            has_audio = True
        else:
            wav = None
            has_audio = False
        n_cues = 0
        audio_dur = total

    audio_label = ("clip" + ("+music" if music_wav else "") if clip_native_audio
                  else ("music" if has_audio else "none"))
    print(f"Beats present: {len(scenes)} | timeline {total:.2f}s | "
          f"mode {asset_mode}/{narration} | motion {motion} | "
          f"audio {audio_label} | {n_cues} caption cue(s)")

    # ---- visuals ----
    # Segments (clips, or images+kenburns) are already at final scale/fps, so
    # their filter chain is just the caption burn, if any. Stills (images, no
    # motion) still need scale/crop/format, with the caption burn appended
    # onto that same chain when present. Either way the final step
    # re-encodes — burning captions rules out a video stream copy regardless
    # of path.
    if asset_mode == "clips":
        seg_dir = tempfile.mkdtemp(prefix="segs_")
        print(f"Rendering {len(scenes)} clip segments with {a.jobs} workers...")
        with ThreadPoolExecutor(max_workers=a.jobs) as ex:
            segs = list(ex.map(render_clip_segment,
                               [(s, frames_dir, seg_dir, clip_native_audio) for s in scenes]))
        listfile, vf = _segments_to_list(segs), burn
    elif motion == "kenburns":
        seg_dir = tempfile.mkdtemp(prefix="segs_")
        print(f"Rendering {len(scenes)} Ken Burns segments with {a.jobs} workers...")
        with ThreadPoolExecutor(max_workers=a.jobs) as ex:
            segs = list(ex.map(render_kenburns_segment, [(s, frames_dir, seg_dir) for s in scenes]))
        listfile, vf = _segments_to_list(segs), burn
    else:
        listfile = build_still_list(scenes, frames_dir)
        base = (f"scale={OUT_WIDTH}:{OUT_HEIGHT}:force_original_aspect_ratio=increase,"
                f"crop={OUT_WIDTH}:{OUT_HEIGHT},format=yuv420p")
        vf = f"{base},{burn}" if burn else base

    if clip_native_audio:
        # Audio comes from the concat input's own stream (each segment carried
        # its clip's generated audio through render_clip_segment), optionally
        # mixed with a ducked music bed. vf is None here (narration == "none"
        # never burns captions), so no -vf is needed on the video stream.
        cmd = ["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", listfile]
        if music_wav:
            cmd += ["-i", music_wav,
                   "-filter_complex",
                   f"[0:a][1:a]amix=inputs=2:duration=first:dropout_transition=0,"
                   f"loudnorm=I={TARGET_LUFS}:TP={TARGET_TP}:LRA={TARGET_LRA}[aout]",
                   "-map", "0:v", "-map", "[aout]"]
        else:
            cmd += ["-map", "0:v", "-map", "0:a",
                   "-af", f"loudnorm=I={TARGET_LUFS}:TP={TARGET_TP}:LRA={TARGET_LRA}"]
        cmd += ["-r", str(OUT_FPS), "-c:v", "libx264", "-crf", str(VIDEO_CRF), "-preset", VIDEO_PRESET,
               "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", out_path]
    else:
        cmd = ["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", listfile]
        if has_audio:
            cmd += ["-i", wav]
        if vf:
            cmd += ["-vf", vf]
        cmd += ["-r", str(OUT_FPS), "-c:v", "libx264", "-crf", str(VIDEO_CRF), "-preset", VIDEO_PRESET]
        if has_audio:
            cmd += ["-c:a", "aac", "-b:a", "192k", "-shortest"]
        else:
            cmd += ["-an"]
        cmd += ["-movflags", "+faststart", out_path]

    print("Encoding...")
    run(cmd)
    os.unlink(listfile)

    dur = float(run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                     "-of", "csv=p=0", out_path]).stdout.strip())
    size = os.path.getsize(out_path) / 1e6
    print(f"\nOK  {out_path}")
    print(f"    {dur:.2f}s | {size:.1f} MB | {OUT_WIDTH}x{OUT_HEIGHT} @ {OUT_FPS}fps"
          f"{'' if has_audio else ' | silent'}")
    if abs(dur - audio_dur) > 0.5:
        print(f"WARN: output {dur:.2f}s vs planned {audio_dur:.2f}s")
    return 0


def _segments_to_list(segs):
    tmp = tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False)
    for s in segs:
        tmp.write(f"file '{s}'\n")
    tmp.close()
    return tmp.name


if __name__ == "__main__":
    sys.exit(main())
