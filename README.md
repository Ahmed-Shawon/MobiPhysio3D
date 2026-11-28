# MobiPhysio 3D

**A Comparative Performance Analysis of 2D and 3D Pose Estimation for Monocular Camera-Based Physiotherapy Exercise Evaluation**

MobiPhysio scores physiotherapy exercises from an ordinary single-camera video. Upload a
video of one of nine exercises and the system returns an assessment score from 0 to 100
and an animated 3D skeleton of the movement.

## How it works

```
video ─► YOLO26-pose (2D keypoints, largest person) ─► KTPFormer (2D → 3D lifting) ─► 3D skeleton GIF
                                     └─► LSTM / GRU encoder (256 features) ─► tuned regressor ─► score 0–100
```

For each exercise, the best combination of encoder (LSTM or GRU), keypoint type (2D or 3D)
and regressor was chosen from the experiments:

| Exercise | Encoder | Keypoints | Regressor | Test MAE |
|---|---|---|---|---|
| Abduction | GRU | 3D | Gradient Boosting | 7.27 |
| Adduction | LSTM | 3D | LightGBM | 21.51 |
| Lateral Rotation | LSTM | 3D | Gradient Boosting | 15.43 |
| Medial Rotation | LSTM | 3D | CatBoost | 9.57 |
| Circumduction | LSTM | 3D | Bagged Decision Trees | 14.47 |
| Wrist Extension | GRU | 2D | Bagged Decision Trees | 7.94 |
| Hip Joint Flexion | GRU | 3D | Random Forest | 16.24 |
| Lumbar Flexion | GRU | 3D | CatBoost | 11.75 |
| Back Extension | LSTM | 3D | CatBoost | 13.00 |

## Repository layout

```
frontend/            Website: plain HTML, CSS and JavaScript (no build step)
  js/config.js       All site settings: text, exercises, backend connection
  assets/demos/      Demo video for each exercise
backend/             FastAPI server; also serves the website
  settings.py        All backend settings (each can be set as an environment variable)
  requirements.txt   Python dependencies (regressor libraries are pinned)
models/
  2Dto3D/            KTPFormer code, YOLO26 pose weights, checkpoint/ (download, see below)
  LSTM/  GRU/        Encoder weights, saved features and tuned parameters per exercise
```

## Setup

Requirements: Python 3.13. An NVIDIA GPU is optional but makes scoring much faster
(about 30 s per video on an RTX 3060).

**1. Clone**

```
git clone https://github.com/Ahmed-Shawon/MobiPhysio3D.git
cd MobiPhysio3D
```

**2. Download the KTPFormer checkpoint** (403 MB, too large for git)

Download `s_128_L_7_C_512_H_8_f_243_ktpformer_cpn_ft_h36m_dbb_best_epoch.bin` from the
[v1.0.0 release](https://github.com/Ahmed-Shawon/MobiPhysio3D/releases/tag/v1.0.0)
and put it in `models/2Dto3D/checkpoint/`.

Or from the terminal:

```
curl -L -o models/2Dto3D/checkpoint/s_128_L_7_C_512_H_8_f_243_ktpformer_cpn_ft_h36m_dbb_best_epoch.bin https://github.com/Ahmed-Shawon/MobiPhysio3D/releases/download/v1.0.0/s_128_L_7_C_512_H_8_f_243_ktpformer_cpn_ft_h36m_dbb_best_epoch.bin
```

**3. Install**

Windows:

```
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Linux / macOS: the same, with `source .venv/bin/activate`.

With an NVIDIA GPU, install PyTorch with CUDA from [pytorch.org](https://pytorch.org) first,
then run `pip install -r requirements.txt`.

**4. Run**

```
uvicorn main:app --port 8000
```

Open **http://localhost:8000**, pick an exercise and upload a video.

The first start takes 1 to 3 minutes: the nine regressors are rebuilt from the saved
features and checked against the reported test metrics. The terminal shows
`Models checked: all 9 OK`. Later starts take seconds.
`http://localhost:8000/api/health` shows whether the GPU is used.

## Accounts and reports

- **Guests** can run assessments without an account. Each result can be downloaded as a
  **PDF report** (exercise, date, score and what it means, the model used, and key frames of
  the video next to the skeleton) and as the **skeleton GIF**.
- **Sign up / log in** (name, email, password) from the navbar. Logged-in users' assessments
  are saved automatically; a guest result can be saved right after signing up.
- **My assessments** (`account.html`): all saved results, score over time per exercise,
  reopen a result, PDF/GIF downloads and a CSV export of the history.
- Data lives in `backend/data/` (SQLite database, saved GIFs and key frames). It is not
  committed. Uploaded videos are never kept. Passwords are hashed with bcrypt; logins use an
  HttpOnly cookie. Set `SECRET_KEY` in the environment, otherwise a random key is created in
  `backend/data/secret_key`. Set `COOKIE_SECURE=1` when the site is served over https.

## Video requirements

- `.mp4`, `.mov`, `.webm` or `.mkv`, between 1 and 60 seconds
- The person must be visible in at least half of the frames. If several people appear,
  the largest one is scored.

## More detail

- [backend/README.md](backend/README.md): settings, the startup check, API and hosting
- [frontend/README.md](frontend/README.md): site settings and the API contract

## Acknowledgements

- 2D pose: [Ultralytics YOLO26](https://github.com/ultralytics/ultralytics) (`yolo26n-pose.pt`)
- 2D to 3D lifting: KTPFormer, fine-tuned on Human3.6M with CPN keypoints

## Contact

Hassan Ahmed Shawon · hassan.a.shawon@gmail.com
