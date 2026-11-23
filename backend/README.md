# MobiPhysio backend

FastAPI server that scores a physiotherapy exercise video and returns a 3D skeleton GIF.
It also serves the website in `../frontend`, so one command runs the whole system.

```
video ─► YOLO26-pose (2D, largest person) ─► KTPFormer (3D) ─► skeleton GIF
                                   └─► LSTM / GRU encoder (256 features) ─► tuned regressor ─► score 0–100
```

The backend imports the model code and weights from `../models/2Dto3D`, `../models/LSTM`
and `../models/GRU`. If `../models/` is missing, it falls back to the original training
folders next to the repo (`PROJECT_ROOT/2Dto3D`, `LSTM`, `GRU`). Each path can be overridden
with the `KTP_DIR`, `LSTM_DIR`, `GRU_DIR`, `YOLO_WEIGHTS` and `KTP_CHECKPOINT` environment variables.

The KTPFormer checkpoint is not in git: download it into `../models/2Dto3D/checkpoint/`
(see the main README).

## Run on your laptop (Windows)

```
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --port 8000
```

Open **http://localhost:8000**, pick an exercise, upload a video.

- First start: about 1–3 minutes. The 9 regressors are rebuilt and checked against your
  results table, then saved to `models_cache/`. Later starts take seconds.
- With an NVIDIA GPU, install PyTorch with CUDA from pytorch.org before the last two
  commands. `http://localhost:8000/api/health` shows `"device": "CUDA"` or `"CPU"`.

## The startup check

The tuned regressors were never saved during training, so they are rebuilt from the saved
hidden-state CSVs with your own `deep_tuning.py` code (same split, top-k features,
best params, seed 42). Each rebuilt model must reproduce your test MAE, RMSE, Pearson and
CCC within a small tolerance (MAE/RMSE ±0.1 points, Pearson/CCC ±0.01, set in `settings.py`);
tiny floating-point differences from a different scikit-learn version are accepted.
The terminal shows one line:

```
Models checked: all 9 OK (5 exact, 4 within tolerance).
```

The full per-metric comparison (rebuilt, expected, difference) is written to
`logs/startup_check.log`. Run it alone with `python regressors.py` (`--rebuild` ignores the cache).
`python tests/check_scoring.py` also runs one processed sample video per exercise from
`2Dto3D/video output/` through the encoder and regressor and compares with your saved
features and predictions. It needs the original training folders next to the repo, which
are not included.

## Settings

All in `settings.py`; each can also be set as an environment variable
(`set MODE=sync` on Windows, `export MODE=sync` on Linux).

| Setting | Default | Meaning |
|---|---|---|
| `MODE` | `poll` | must match `MODE` in `frontend/js/config.js`. `sync` is fine on a fast GPU. |
| `DEVICE` | `auto` | `cpu` or `cuda` to force |
| `MIN_VIDEO_SECONDS` / `MAX_VIDEO_SECONDS` | 1 / 60 | allowed video length |
| `MIN_PERSON_FRACTION` | 0.5 | person must be visible in at least 50% of frames |
| `MAX_GIF_FRAMES` | 150 | frames in the skeleton GIF (0 = whole video) |
| `QUEUE_MAX` | 3 | videos waiting behind the running one before "server busy" |
| `JOB_TTL_HOURS` | 24 | results and GIFs are deleted after this |
| `STRICT_CHECK` | 1 | 0 = start even if the startup check fails (not recommended) |

Accepted files: .mp4, .mov, .webm, .mkv. No size limit. Uploaded videos are deleted after
processing. Logs go to `logs/backend.log`.

## API

| Request | Response |
|---|---|
| `POST /api/analyze` (form: `video`, `exercise_id`) | poll mode `{"job_id"}`; sync mode the result |
| `GET /api/status/{job_id}` | `{"status": "queued/processing/scoring/done/failed", ...}` |
| result | `{"score", "skeleton_url", "details"}` |
| `GET /outputs/<job>.gif` | skeleton GIF |
| `GET /api/health` | `{"ready", "device", "mode", "exercises"}` |

Errors return `{"detail": "message"}`, which the site shows: unsupported exercise (400),
no video (400), wrong file type (415), unreadable video, too short, too long, no person,
person visible in under 50% of frames (422), not ready or busy (503), other failure (500).
Several people in the video is not an error: the largest person is scored.

## Hosting on a Hostinger VPS (later)

Shared web hosting cannot run PyTorch; a VPS (KVM plan, about 8 GB RAM) can, on CPU.
Clone the repo, download the checkpoint, install as above, and run
`uvicorn main:app --host 0.0.0.0 --port 8000` behind nginx. Keep `MODE` = `poll`.
