"""Key frames for the PDF report: a few frames of the uploaded video next to the
matching frames of the skeleton GIF. Taken right after scoring, before the video is
deleted. Only small JPEGs are kept, never the video."""
import logging
from pathlib import Path

import cv2
from PIL import Image

import settings

log = logging.getLogger("mobiphysio.keyframes")
MAX_SIDE = 520


def _fractions(n):
    # e.g. 3 -> 0.2, 0.5, 0.8 of the way through the clip
    return [0.5] if n == 1 else [0.2 + 0.6 * i / (n - 1) for i in range(n)]


def _shrink(img: Image.Image) -> Image.Image:
    img = img.convert("RGB")
    img.thumbnail((MAX_SIDE, MAX_SIDE))
    return img


def extract(video_path: Path, gif_path: Path, out_dir: Path, n=None):
    """Writes input_<i>.jpg and skeleton_<i>.jpg into out_dir. Returns [(input, skeleton), ...].
    Never raises: a report without key frames is better than a failed assessment."""
    n = n or settings.KEYFRAMES
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        cap = cv2.VideoCapture(str(video_path))
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
        gif = Image.open(gif_path)
        gif_total = getattr(gif, "n_frames", 1)
        pairs = []
        for i, f in enumerate(_fractions(n)):
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(f * max(total - 1, 0)))
            ok, frame = cap.read()
            if not ok:
                continue
            gif.seek(int(f * max(gif_total - 1, 0)))
            a, b = out_dir / f"input_{i}.jpg", out_dir / f"skeleton_{i}.jpg"
            _shrink(Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))).save(a, quality=85)
            _shrink(gif.copy()).save(b, quality=85)
            pairs.append((a, b))
        cap.release()
        return pairs
    except Exception:
        log.exception("Could not take key frames for the report")
        return []
