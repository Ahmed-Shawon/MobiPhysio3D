"""
Video -> 2D keypoints (YOLO26-pose) -> 3D (KTPFormer) -> skeleton GIF -> features -> score.

Reuses your code from 2Dto3D/ (coco_to_h36m17, save_as_csv, predict_3d, plot_skeleton)
and from LSTM/ + GRU/ (the encoder classes and pose_dataset normalisation), imported
by path. Only the person selection differs from video_to_3d.py: when several people
are in a frame, the LARGEST one (bounding box area) is kept.
"""
import logging
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import pandas as pd

import settings
from errors import UserError
from loader import load_module
from routing import EXERCISES

log = logging.getLogger("mobiphysio.pipeline")


# ------------------------------------------------------------------ video checks
def probe_video(path: Path):
    """Returns (frames, fps, width, height, seconds) or raises UserError."""
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise UserError(422, "This file could not be read as a video.")
    fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    ok, _ = cap.read()
    if frames <= 0 and ok:  # some .webm/.mkv files do not store a frame count: count them
        frames = 1
        while cap.grab():
            frames += 1
    cap.release()
    if not ok or frames <= 0 or width <= 0 or height <= 0:
        raise UserError(422, "This file could not be read as a video.")
    if fps <= 0 or fps > 1000:
        fps = 30.0  # unknown frame rate; assume 30
    return frames, fps, width, height, frames / fps


def check_length(seconds: float):
    if seconds < settings.MIN_VIDEO_SECONDS:
        raise UserError(422, f"The video is {seconds:.0f} s long. "
                             f"It must be at least {settings.MIN_VIDEO_SECONDS:.0f} s.")
    if seconds > settings.MAX_VIDEO_SECONDS:
        raise UserError(422, f"The video is {seconds:.0f} s long. "
                             f"The limit is {settings.MAX_VIDEO_SECONDS:.0f} s.")


# ------------------------------------------------------------------ engine
class Engine:
    """Holds every model in memory. Created once at startup."""

    def __init__(self, regressor_entries: dict):
        import torch
        self.torch = torch
        self.regressors = regressor_entries
        self.device = self._pick_device()

        # 2Dto3D code (needs its folder on sys.path for `common.*`)
        if str(settings.KTP_DIR) not in sys.path:
            sys.path.insert(0, str(settings.KTP_DIR))
        self.inf = load_module(settings.KTP_DIR / "infer_2d_to_3d.py", "infer_2d_to_3d")
        self.v2d = load_module(settings.KTP_DIR / "video_to_3d.py", "video_to_3d")
        self.bps = load_module(settings.KTP_DIR / "batch_process_subject.py", "batch_process_subject")

        self._load_vision_models()

        # encoders (one per exercise; small)
        self.encoders = {}
        self.datasets = {}
        for code, ex in EXERCISES.items():
            folder = ex.folder
            cls_mod = load_module(folder / f"{ex.encoder.lower()}_regressor.py",
                                  f"{ex.encoder.lower()}_regressor", folder)
            ds_mod = load_module(folder / "pose_dataset.py", f"pose_dataset_{ex.encoder.lower()}", folder)
            cls = cls_mod.LSTMRegressor if ex.encoder == "LSTM" else cls_mod.GRURegressor
            model = cls(input_dim=34 if ex.modality == "2d" else 51)
            state = torch.load(ex.encoder_weights, map_location="cpu")
            model.load_state_dict(state)
            model.eval()
            self.encoders[code] = model
            self.datasets[code] = ds_mod.PoseSequenceDataset

    def _pick_device(self):
        want = settings.DEVICE.lower()
        if want == "cuda" or (want == "auto" and self.torch.cuda.is_available()):
            return "cuda"
        return "cpu"

    def _load_vision_models(self):
        from ultralytics import YOLO
        self.inf.DEVICE = self.device
        self.inf.CHECKPOINT_PATH = str(settings.KTP_CHECKPOINT)
        self.ktp = self.inf.load_model()
        self.yolo = YOLO(str(settings.YOLO_WEIGHTS))
        self.skeleton_parents = self.inf.build_h36m_17j_skeleton().parents()
        log.info("YOLO26-pose and KTPFormer loaded on %s", self.device.upper())

    def fall_back_to_cpu(self):
        log.warning("GPU ran out of memory: switching to CPU")
        self.device = "cpu"
        self.torch.cuda.empty_cache()
        self._load_vision_models()

    # -------------------------------------------------------------- stage 1: 2D
    def extract_2d(self, video_path: Path):
        """COCO-17 keypoints (T,17,2) of the largest person per frame, plus person stats."""
        frames_kp, n_people = [], []
        yolo_device = 0 if self.device == "cuda" else "cpu"
        for r in self.yolo(str(video_path), stream=True, verbose=False, device=yolo_device):
            kp = None
            confident = 0
            if r.keypoints is not None and r.boxes is not None and len(r.boxes) > 0:
                xyxy = r.boxes.xyxy.cpu().numpy()
                conf = r.boxes.conf.cpu().numpy()
                area = (xyxy[:, 2] - xyxy[:, 0]) * (xyxy[:, 3] - xyxy[:, 1])
                best = int(np.argmax(area))                      # largest person
                kp = r.keypoints.xy[best].cpu().numpy()
                confident = int((conf >= settings.PERSON_CONF).sum())
            frames_kp.append(kp)
            n_people.append(confident)

        total = len(frames_kp)
        detected = sum(k is not None for k in frames_kp)
        if total == 0:
            raise UserError(422, "This file could not be read as a video.")
        if detected == 0:
            raise UserError(422, "No person was detected in the video.")
        fraction = detected / total
        if fraction < settings.MIN_PERSON_FRACTION:
            raise UserError(422, f"A person was visible in only {fraction:.0%} of the video. "
                                 "Keep the whole body in frame.")

        # fill gaps exactly like video_to_3d.extract_2d_keypoints: forward, then back-fill the start
        last = None
        for i, k in enumerate(frames_kp):
            if k is None:
                frames_kp[i] = last
            else:
                last = k
        first = next(k for k in frames_kp if k is not None)
        frames_kp = [k if k is not None else first for k in frames_kp]

        n_people = np.array(n_people)
        several = float((n_people >= 2).mean())
        return np.stack(frames_kp, axis=0), {"fraction": fraction, "several_people_fraction": several,
                                             "max_people": int(n_people.max())}

    # -------------------------------------------------------------- stage 2 + 3: 3D + GIF
    def lift_3d(self, coco_kp, width, height):
        h36m_2d = self.v2d.coco_to_h36m17(coco_kp)
        pred_3d = self.inf.predict_3d(self.ktp, h36m_2d, width, height)
        return h36m_2d, pred_3d

    def render_gif(self, pred_3d, gif_path: Path):
        # Same picture as batch_process_subject.plot_skeleton, drawn faster
        # (plot built once + frames drawn on several CPU cores). See skeleton_gif.py.
        import skeleton_gif
        skeleton_gif.render(pred_3d, self.skeleton_parents, gif_path, fps=settings.GIF_FPS,
                            max_frames=settings.MAX_GIF_FRAMES, workers=settings.GIF_WORKERS)

    # -------------------------------------------------------------- stage 4: score
    def encode(self, code, csv_2d: Path, csv_3d: Path):
        """Loads the CSVs through YOUR PoseSequenceDataset (same rounding + normalisation
        as training) and returns the encoder's 256 hidden features."""
        ex = EXERCISES[code]
        manifest = pd.DataFrame({"video_name": ["upload"], "average_score": [0.0],
                                 "csv_2d": [str(csv_2d)], "csv_3d": [str(csv_3d)]})
        ds = self.datasets[code](manifest, ex.modality, score_mean=0.0, score_std=1.0)
        item = ds[0]
        seq = item["sequence"].unsqueeze(0)                 # (1, T, 34 or 51)
        lengths = self.torch.tensor([item["length"]], dtype=self.torch.long)
        with self.torch.no_grad():
            hidden = self.encoders[code].get_hidden_state(seq, lengths)
        return hidden.cpu().numpy()[0]

    # -------------------------------------------------------------- full run
    def analyze(self, video_path: Path, code: str, job_id: str, on_stage=lambda s: None):
        from regressors import predict
        ex = EXERCISES[code]
        t0 = time.time()

        frames, fps, width, height, seconds = probe_video(video_path)
        check_length(seconds)

        on_stage("processing")
        work = settings.OUTPUT_DIR / job_id
        work.mkdir(parents=True, exist_ok=True)
        gif_path = settings.OUTPUT_DIR / f"{job_id}.gif"

        def vision():
            coco, people = self.extract_2d(video_path)
            h36m_2d, pred_3d = self.lift_3d(coco, width, height)
            return people, h36m_2d, pred_3d

        try:
            people, h36m_2d, pred_3d = vision()
        except self.torch.cuda.OutOfMemoryError:
            self.fall_back_to_cpu()
            people, h36m_2d, pred_3d = vision()

        csv_2d, csv_3d = work / "input_2d_h36m.csv", work / "output_3d.csv"
        self.v2d.save_as_csv(h36m_2d, str(csv_2d))
        self.v2d.save_as_csv(pred_3d, str(csv_3d))
        self.render_gif(pred_3d, gif_path)

        on_stage("scoring")
        features = self.encode(code, csv_2d, csv_3d)
        raw = predict(self.regressors[code], features)
        score = float(np.clip(raw, 0.0, 100.0))

        # (the site already shows Exercise, Video file and Processing time itself)
        details = {
            "Model": ex.model_label,
            "Expected error": f"±{ex.reference['MAE']:.2f} points (test MAE)",
            "Video length": f"{seconds:.1f} s",
            "Frames analysed": int(pred_3d.shape[0]),
            "Person visible": f"{people['fraction']:.0%} of frames",
        }
        if people["several_people_fraction"] > 0.2:
            details["People detected"] = f"up to {people['max_people']}, the largest was scored"
        if raw != score:
            details["Note"] = f"score clipped from {raw:.2f}"
        log.info("Job %s: %s scored %.2f in %.0f s", job_id, ex.name, score, time.time() - t0)
        details["Device"] = "GPU" if self.device == "cuda" else "CPU"

        return {"score": round(score, 2),
                "skeleton_url": f"/outputs/{gif_path.name}",
                "details": details}
