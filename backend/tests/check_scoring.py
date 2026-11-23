"""
Checks the scoring half of the pipeline against your training results, using the
keypoint CSVs already in 2Dto3D/video output/ (no YOLO or KTPFormer needed).

For each exercise it takes the first processed sample video, runs it through the
encoder + rebuilt regressor exactly as the server does, and compares:
  - the 256 encoder features with that video's row in <encoder>_states_*.csv
  - the score with that video's prediction in final_predictions_all.csv

Needs the original training folders (2Dto3D, LSTM, GRU) next to RehabSite.
Run from RehabSite/backend:
    python tests/check_scoring.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import settings  # noqa: E402
from pipeline import Engine  # noqa: E402
from regressors import prepare_all, predict  # noqa: E402
from routing import EXERCISES  # noqa: E402

# Training outputs are not shipped in the repo; this check reads them from the
# original training folders next to RehabSite (PROJECT_ROOT).
SAMPLES = settings.PROJECT_ROOT / "2Dto3D" / "video output"


def _predictions_csv(ex):
    return settings.PROJECT_ROOT / ex.encoder / "final_predictions_all.csv"


def main():
    Engine._load_vision_models = lambda self: None     # scoring only: skip YOLO + KTPFormer
    entries = prepare_all()
    engine = Engine(entries)
    failures = 0

    for code, ex in EXERCISES.items():
        folders = sorted(p for p in SAMPLES.glob(f"{code}_*") if (p / "output_3d.csv").exists())
        if not folders:
            print(f"{ex.name:<18} no sample in '{SAMPLES.name}', skipped")
            continue
        video = folders[0]
        feats = engine.encode(code, video / "input_2d_h36m.csv", video / "output_3d.csv")

        states = pd.read_csv(ex.states_csv)
        row = states[states["video_name"] == video.name]
        hidden_cols = [c for c in states.columns if c.startswith("hidden_")]
        feat_diff = float(np.abs(row[hidden_cols].to_numpy()[0] - feats).max()) if len(row) else None

        score = predict(entries[code], feats)
        pred_csv = _predictions_csv(ex)
        if pred_csv.is_file():
            preds = pd.read_csv(pred_csv)
            p = preds[(preds.video_name == video.name) & (preds.modality == ex.modality)]
            score_diff = abs(float(p["pred"].iloc[0]) - score) if len(p) else None
        else:
            score_diff = None

        ok = (feat_diff is None or feat_diff < 1e-4) and (score_diff is None or score_diff < 0.01)
        failures += not ok
        print(f"{ex.name:<18} {video.name:<22} score {score:6.2f}  "
              f"feature diff {feat_diff if feat_diff is not None else 'n/a'}  "
              f"score diff {score_diff if score_diff is not None else 'n/a'}  {'OK' if ok else 'MISMATCH'}")

    print("All checks passed." if not failures else f"{failures} exercise(s) did not match.")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
