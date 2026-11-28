"""
All backend settings in one place.

Every value can be overridden with an environment variable of the same name,
e.g.  set MODE=sync   (Windows)   or   export MODE=sync   (Linux / VPS).
"""
import os
from pathlib import Path


def _env(name, default):
    return os.environ.get(name, default)


# ---------------------------------------------------------------- folders
BACKEND_DIR = Path(__file__).resolve().parent
# Capstone_Dashboard/  (RehabSite/backend -> RehabSite -> Capstone_Dashboard)
PROJECT_ROOT = Path(_env("PROJECT_ROOT", BACKEND_DIR.parent.parent)).resolve()
FRONTEND_DIR = Path(_env("FRONTEND_DIR", BACKEND_DIR.parent / "frontend")).resolve()

# Model code and weights. RehabSite/models/ (shipped with the repo) is used when it
# exists; otherwise the original training folders next to RehabSite are used.
MODELS_DIR = Path(_env("MODELS_DIR", BACKEND_DIR.parent / "models")).resolve()


def _model_dir(name):
    bundled = MODELS_DIR / name
    return bundled if bundled.is_dir() else PROJECT_ROOT / name


KTP_DIR = Path(_env("KTP_DIR", _model_dir("2Dto3D")))      # KTPFormer code + YOLO weights
LSTM_DIR = Path(_env("LSTM_DIR", _model_dir("LSTM")))
GRU_DIR = Path(_env("GRU_DIR", _model_dir("GRU")))

KTP_CHECKPOINT_NAME = "s_128_L_7_C_512_H_8_f_243_ktpformer_cpn_ft_h36m_dbb_best_epoch.bin"
_ktp_candidates = [
    KTP_DIR / "checkpoint" / KTP_CHECKPOINT_NAME,   # repo layout (download from the GitHub release)
    PROJECT_ROOT / "2Dto3D" / "checkpoint" / "log" / "default_20261004T15-44-59" / KTP_CHECKPOINT_NAME,
]

YOLO_WEIGHTS = Path(_env("YOLO_WEIGHTS", KTP_DIR / "yolo26n-pose.pt"))
KTP_CHECKPOINT = Path(_env(
    "KTP_CHECKPOINT",
    next((p for p in _ktp_candidates if p.is_file()), _ktp_candidates[0]),
))

UPLOAD_DIR = BACKEND_DIR / "uploads"
OUTPUT_DIR = BACKEND_DIR / "outputs"
CACHE_DIR = BACKEND_DIR / "models_cache"
LOG_DIR = BACKEND_DIR / "logs"
# Accounts database, saved assessments (GIF + key frames) and the secret key. Never committed.
DATA_DIR = Path(_env("DATA_DIR", BACKEND_DIR / "data")).resolve()
DB_PATH = DATA_DIR / "mobiphysio.db"
SAVED_DIR = DATA_DIR / "assessments"

# ---------------------------------------------------------------- runtime
# "auto" = GPU if available, else CPU.  "cpu" or "cuda" to force.
DEVICE = _env("DEVICE", "auto")

# Must match MODE in frontend/js/config.js
#   "poll" = POST returns a job id, the site asks /api/status/{job_id} (works everywhere)
#   "sync" = POST waits and returns the result (fine on a fast GPU)
MODE = _env("MODE", "poll")

# Jobs waiting behind the one that is running; more than this -> "server busy"
QUEUE_MAX = int(_env("QUEUE_MAX", 3))
# Finished jobs (and their GIFs) are forgotten after this many hours
JOB_TTL_HOURS = float(_env("JOB_TTL_HOURS", 24))

# ---------------------------------------------------------------- upload rules
ALLOWED_EXTENSIONS = {".mp4", ".mov", ".webm", ".mkv"}
MIN_VIDEO_SECONDS = float(_env("MIN_VIDEO_SECONDS", 1))
MAX_VIDEO_SECONDS = float(_env("MAX_VIDEO_SECONDS", 60))
# No file size limit (agreed).

# ---------------------------------------------------------------- person checks
PERSON_CONF = float(_env("PERSON_CONF", 0.5))           # a detection counts as a person above this
MIN_PERSON_FRACTION = float(_env("MIN_PERSON_FRACTION", 0.5))  # person must be in >= 50% of frames
# Several people: not an error. The largest person in each frame is scored.

# ---------------------------------------------------------------- outputs
MAX_GIF_FRAMES = int(_env("MAX_GIF_FRAMES", 0))   # 0 = whole video
GIF_FPS = int(_env("GIF_FPS", 25))
# CPU processes that draw the skeleton GIF at the same time. 0 = automatic (cores - 1, at most 6)
GIF_WORKERS = int(_env("GIF_WORKERS", 0))

# ---------------------------------------------------------------- accounts
# Signs the login cookies. Set SECRET_KEY in the environment; if it is not set, a random
# key is created once and kept in data/secret_key (so logins survive a restart).
SECRET_KEY = _env("SECRET_KEY", "")
SESSION_DAYS = float(_env("SESSION_DAYS", 30))
SESSION_COOKIE = "mp_session"
# "1" when the site is served over https (the cookie is then only sent over https)
COOKIE_SECURE = _env("COOKIE_SECURE", "0") == "1"
KEYFRAMES = 3           # input / skeleton frame pairs in the PDF report

# ---------------------------------------------------------------- startup check
SEED = 42
CHECK_DECIMALS = 4      # decimals shown in logs/startup_check.log
# Small floating-point differences (e.g. a different scikit-learn version) are accepted.
# The server only refuses to start if a rebuilt model is further off than this:
CHECK_TOLERANCE_POINTS = float(_env("CHECK_TOLERANCE_POINTS", 0.1))   # MAE and RMSE, score points
CHECK_TOLERANCE_CORR = float(_env("CHECK_TOLERANCE_CORR", 0.01))      # Pearson and CCC
STRICT_CHECK = _env("STRICT_CHECK", "1") != "0"   # "0" = start even if a model is outside the tolerance

for d in (UPLOAD_DIR, OUTPUT_DIR, CACHE_DIR, LOG_DIR, DATA_DIR, SAVED_DIR):
    d.mkdir(parents=True, exist_ok=True)

if not SECRET_KEY:
    _key_file = DATA_DIR / "secret_key"
    if not _key_file.is_file():
        import secrets as _secrets
        _key_file.write_text(_secrets.token_hex(32), encoding="utf-8")
    SECRET_KEY = _key_file.read_text(encoding="utf-8").strip()
