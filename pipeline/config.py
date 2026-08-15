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
#     clips  -> OpenArt Kling 2.5 video clips, stitched, fixed at
#               CLIPS_PER_SHORT beats
#   narration: "full" | "none"
#     full -> voiced script (30-45s average), TTS, burned captions from the
#             transcript
#     none -> no voice-over; burned beat labels over music
VALID_ASSET_MODES = ("images", "clips")
VALID_NARRATION = ("full", "none")

# ---------- beat count ----------
# Fixed per asset_mode, not derived from script length or novelty-detection —
# every Short from this pipeline has exactly this many beats regardless of
# how long the script is. A script that's louder in some places than others
# still divides into this many beats; the timing bends, the count doesn't.
IMAGES_PER_SHORT = 5
CLIPS_PER_SHORT = 4

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
# script to derive scene boundaries from, and because the count is fixed
# (IMAGES_PER_SHORT / CLIPS_PER_SHORT above) rather than algorithmically
# derived — these floors/caps exist only to catch a beat that ends up
# absurdly short or long once the fixed count is divided into the total
# duration, not to drive the cutting decision itself.
BEAT_MIN_SEC = 1.5
BEAT_SOFT_MAX_SEC = 15.0
BEAT_HARD_MAX_SEC = 25.0

# ---------- captions / text overlay ----------
SRT_MAX_WORDS_PER_CUE = 4   # tighter than long-form; a Short's captions read in a glance
FONT = "DejaVu Sans"
FONT_SIZE = 64
TEXT_SAFE_MARGIN_PX = 90     # keep burned text clear of the UI overlap zone on Shorts/Reels

# ---------- images (asset_mode == "images") ----------
IMAGE_MODEL = "nano-banana-2"
IMAGE_MODE = "text2image"
IMAGE_RESOLUTION = "2K"
IMAGE_ASPECT = "9:16"        # native vertical — no letterbox/crop step needed downstream
IMAGE_COUNT = 1               # images returned per individual OpenArt call, not beats per Short
AUTO_ENHANCE_PROMPT = False  # ALWAYS false - it rewrites the locked style block
MIN_IMAGE_BYTES = 10000

# ---------- clips (asset_mode == "clips") ----------
# Kling 2.5 via OpenArt. Confirm the exact model id string against
# openart_model_list before the first real run — "kling-2.5" below is the
# human name given, not a verified API identifier.
VIDEO_MODEL = "kling-2.5"
VIDEO_ASPECT = "9:16"
VIDEO_QUALITY_MODE = "quality"   # as opposed to a faster/draft mode, if OpenArt exposes one
VIDEO_AUDIO = False              # clip audio off — this pipeline's own narration/music track
                                  # is the only audio in the final output, never the clip's own
VIDEO_CLIP_SEC = 5.0             # length OpenArt renders per submission; beats longer than
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
