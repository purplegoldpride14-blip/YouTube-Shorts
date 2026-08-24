"""
Single source of truth for every pipeline constant.

RULE: if a number appears in PROCESS.md, SKILL.md, or a playbook, it is a
comment describing this file, not an independent statement of fact. If they
disagree, this file wins.

This pipeline produces standalone vertical Shorts, not long-form video. There
is no separate landscape/portrait split like the parent pipeline had — the
output IS the Short.
"""

# ---------- project modes ----------
# Set per-project in project.json, not here.
#   asset_mode: "images" | "clips"
#     images -> OpenArt Nano Banana 2 stills, Ken Burns motion, fixed at
#               IMAGES_PER_SHORT beats
#     clips  -> OpenArt Gemini Omni Flash video clips, stitched, fixed at
#               CLIPS_PER_SHORT beats. Native synchronized audio (dialogue,
#               SFX, music) — the clip's OWN generated audio is kept in the
#               output for narration == "none" projects, see VIDEO_AUDIO.
#   narration: "full" | "none"
#     full -> voiced script (30-45s average), TTS, burned captions from the
#             transcript. asset_mode == "clips" here still strips each
#             clip's own generated audio (VIDEO_AUDIO doesn't apply) so it
#             can't clash with the read narration track.
#     none -> no burned text of any kind. asset_mode == "images": silent or
#             scored by the audio field below. asset_mode == "clips" with
#             VIDEO_AUDIO True: each clip's own generated dialogue/audio IS
#             the soundtrack — audio below only decides whether a music bed
#             is ALSO mixed in underneath it, ducked.
#   audio: "music" | "none" (narration == "none" projects only — a "full"
#          project's audio is always its narration track)
#     asset_mode == "images":
#       music -> audio/music.* looped/trimmed to a bed under the visuals
#       none  -> no audio track in the output at all
#     asset_mode == "clips" (VIDEO_AUDIO True):
#       music -> audio/music.* mixed in underneath the clips' own audio,
#                ducked (ties to MUSIC_DUCK_LUFS, not MUSIC_BED_LUFS)
#       none  -> the clips' own generated audio only, no added music bed
VALID_ASSET_MODES = ("images", "clips")
VALID_NARRATION = ("full", "none")
VALID_AUDIO = ("music", "none")

# ---------- beat count ----------
# Fixed per asset_mode, not derived from script length or novelty-detection —
# every Short from this pipeline has exactly this many beats regardless of
# how long the script is. A script that's louder in some places than others
# still divides into this many beats; the timing bends, the count doesn't.
IMAGES_PER_SHORT = 7
CLIPS_PER_SHORT = 5

# asset_mode == "images", narration == "none" only: beats are always
# equal-length, IMAGES_TOTAL_DURATION_SEC split evenly across
# IMAGES_PER_SHORT beats — scene_plan.py's "beats" command computes each
# beat's duration from this rather than reading "dur" out of beats.json, so
# the only editorial call left there is each beat's label. narration ==
# "full" images shorts are unaffected — their timing still comes from the
# actual narration length, and asset_mode == "clips" still states "dur" per
# beat by hand.
# 28.0 / 7 = 4.0s per beat, matching the clips path's 4s-per-beat pacing.
IMAGES_TOTAL_DURATION_SEC = 28.0

# ---------- script (narration == "full" only) ----------
# Averages 30-45s of narration at a brisk pace (~2.5-2.6 words/sec measured
# against this pipeline's own TTS tests). WORDS_MIN/MAX is the target band;
# HARD_MIN/MAX is what script_check.py actually enforces.
WORDS_MIN = 80
WORDS_MAX = 115
WORDS_HARD_MIN = 65
WORDS_HARD_MAX = 130

TTS_CHAR_CAP = 10000       # engine hard limit per submission; a Short is one part in practice
TTS_CHAR_TARGET = 9500

# ---------- narration safety (see narration_lint.py) ----------
DASH_CHARS = ["\u2014", "\u2013", "\u2012", "\u2015", "\u2212"]  # em, en, figure, bar, minus
LINT_STRICT_DEFAULT = False

# ---------- description ----------
DESCRIPTION_CHAR_CAP = 5000
DESCRIPTION_WORD_MIN = 40   # a Short's description is a line or two, not a long-form essay
DESCRIPTION_NO_HASHTAGS = False  # Shorts lean on #shorts + niche tags; override per project

# ---------- audio ----------
WAV_RATE = 44100
WAV_CHANNELS = 1
TARGET_LUFS = -14.0
TARGET_TP = -1.5
TARGET_LRA = 11.0
LOUDNESS_TOLERANCE = 1.0

# music bed, used when narration == "none" (and ducked under narration when "full"
# if a music track is also present)
MUSIC_BED_LUFS = -23.0        # quieter than narration; a bed, not a competing signal
MUSIC_DUCK_LUFS = -30.0       # further ducked under the narration track itself

# ---------- beats (scene/clip timing) ----------
# A "beat" is this pipeline's unit — one image or one clip on screen. Named
# beats rather than "scenes" because narration == "none" shorts have no
# script to derive scene boundaries from.
#
# asset_mode == "clips", and asset_mode == "images" with narration == "none",
# both use the fixed count above (CLIPS_PER_SHORT / IMAGES_PER_SHORT) — these
# floors/caps exist only to catch a beat that ends up absurdly short or long
# once that fixed count is divided into the total duration, not to drive the
# cutting decision itself.
#
# asset_mode == "images" with narration == "full" is different: the beat
# count isn't fixed at all — scene_plan.py cuts one beat per sentence (natural
# pause points), merging a sentence that alone would fall under BEAT_MIN_SEC
# into its neighbor, and splitting one that alone would run over
# BEAT_SOFT_MAX_SEC at the nearest comma. Here these floors/caps DO drive the
# cutting decision, not just validate it after the fact.
BEAT_MIN_SEC = 1.5
BEAT_SOFT_MAX_SEC = 15.0
BEAT_HARD_MAX_SEC = 25.0

# Safety cap only for the natural-cut path above (asset_mode == "images",
# narration == "full") — stops a script written in unusually short, staccato
# sentences from fragmenting into an excessive number of image generations
# (each one real OpenArt credits). Beats are merged pairwise, shortest gap
# first, until the count is at or under this — never a target to hit, only a
# ceiling.
IMAGES_NATURAL_MAX_BEATS = 12

# ---------- captions / text overlay ----------
SRT_MAX_WORDS_PER_CUE = 4   # tighter than long-form; a Short's captions read in a glance
FONT = "DejaVu Sans"
FONT_SIZE = 84               # large enough to read at a glance on a phone

# YouTube Shorts burns its own UI (title, channel handle, description,
# like/comment/share rail) over roughly the bottom quarter to third of the
# player, and that overlay isn't present in the raw file we assemble - so a
# fixed small bottom margin looks fine here but gets covered once uploaded.
# Anchored to a fraction of OUT_HEIGHT (not a fixed pixel count) so it holds
# up if OUT_HEIGHT ever changes: this is the distance from the bottom edge
# to the caption's anchor line, pushing the caption block up toward vertical
# center and comfortably clear of that reserved UI zone.
CAPTION_MARGIN_V_FRAC = 0.45

# ---------- images (asset_mode == "images") ----------
IMAGE_MODEL = "nano-banana-2"
IMAGE_MODE = "text2image"
IMAGE_RESOLUTION = "2K"
IMAGE_ASPECT = "9:16"        # native vertical — no letterbox/crop step needed downstream
IMAGE_COUNT = 1               # images returned per individual OpenArt call, not beats per Short
AUTO_ENHANCE_PROMPT = False  # ALWAYS false - it rewrites the locked style block
MIN_IMAGE_BYTES = 10000

# ---------- clips (asset_mode == "clips") ----------
# Google Gemini Omni Flash via OpenArt (model id "gemini-omni-flash",
# mode "text2video"). Verified against openart_model_list /
# openart_model_cost directly — no "veo-3.1" model exists in OpenArt's
# catalog, and this is the closest available: Google-made, native
# synchronized audio (dialogue, SFX, music) baked into every generation,
# not a togglable field. There is no resolution or quality-tier parameter
# exposed for this model — output resolution isn't selectable through
# OpenArt. At duration 4 / aspectRatio "9:16" this costs 200 credits per
# clip (openart_model_cost, verified). Duration accepts any integer 3-10.
#
# Fallback, if Gemini's dialogue quality isn't good enough: OpenArt's own
# model description names "byte-plus-seedance-2" (displayName "Seedance
# 2.0") as "the pick for video with a spoken voice" — 400 credits per 5s
# clip at 720p with generateAudio true, real resolution/duration control.
# Swap VIDEO_MODEL/VIDEO_MODE below and re-verify params with
# openart_model_form_get before the next run if switching.
VIDEO_MODEL = "gemini-omni-flash"
VIDEO_MODE = "text2video"
VIDEO_ASPECT = "9:16"
VIDEO_AUDIO = True                # native to this model - the clip's own generated audio
                                   # (dialogue etc.) is kept for narration == "none" projects;
                                   # narration == "full" still strips it (see project modes above)
VIDEO_CLIP_SEC = 4.0              # length OpenArt renders per submission; beats longer than
                                   # this loop the clip, beats shorter than this trim it
MIN_VIDEO_BYTES = 200000

# ---------- video output ----------
OUT_WIDTH = 1080
OUT_HEIGHT = 1920
OUT_FPS = 30
VIDEO_CRF = 18
VIDEO_PRESET = "medium"
MOTION_DEFAULT = "kenburns"      # applies to asset_mode == "images" only
KENBURNS_ZOOM = 1.10             # a touch more travel than long-form; the frame is on screen
                                  # for seconds not minutes, so it needs to read as movement fast

# ---------- duration ----------
DURATION_MIN_SEC = 15      # below this, a clip is too thin to stand alone - WARN
DURATION_SOFT_MAX_SEC = 90 # above this, retention drops off - WARN
DURATION_HARD_MAX_SEC = 180  # YouTube Shorts' technical cap - FAIL

# ---------- delivery ----------
GIT_PUSH_MAX_BYTES = 95_000_000
CHAT_CHUNK_BYTES = 25 * 1024 * 1024

# ---------- required network domains ----------
# Must be allowlisted BEFORE the run starts. Cannot be changed mid-session.
REQUIRED_DOMAINS = ["storage.googleapis.com", "cdn.openart.ai"]
