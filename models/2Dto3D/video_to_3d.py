"""
Video -> 2D (YOLO26-pose) -> 3D (KTPFormer) -> skeleton visuals -> CSV.

This is video_to_3d.py and npy_to_csv.py merged into one file: each video
now gets its .npy AND .csv files written together in the same pass, no
separate conversion script/step needed afterward.

Install once:
    pip install ultralytics opencv-python-headless

Usage:
    python video_to_3d.py --video-dir "video dataset" --output-root video_output
    python video_to_3d.py --video-dir "video dataset" --checkpoint log/default_XXXX/best.bin
"""

import os
import csv
import argparse
import numpy as np
import cv2
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D  # noqa: F401
from matplotlib.animation import FuncAnimation
from ultralytics import YOLO

import infer_2d_to_3d as inf
from batch_process_subject import plot_skeleton  # reuse the exact same plotting code


# ============================== CONFIG (defaults, overridable via CLI) ==============================
VIDEO_DIR          = "video dataset"     # folder containing your .mp4 files
OUTPUT_ROOT        = "video_output"      # everything goes under video_output/<video_name>/
YOLO_WEIGHTS       = "yolo26n-pose.pt"   # auto-downloaded on first run
MAX_FRAMES_FOR_GIF = 150
# ======================================================================================================


# COCO-17 (YOLO26-pose) joint order:
# 0 nose, 1 l_eye, 2 r_eye, 3 l_ear, 4 r_ear, 5 l_shoulder, 6 r_shoulder,
# 7 l_elbow, 8 r_elbow, 9 l_wrist, 10 r_wrist, 11 l_hip, 12 r_hip,
# 13 l_knee, 14 r_knee, 15 l_ankle, 16 r_ankle
COCO_NOSE, COCO_LSHO, COCO_RSHO = 0, 5, 6
COCO_LELB, COCO_RELB = 7, 8
COCO_LWRI, COCO_RWRI = 9, 10
COCO_LHIP, COCO_RHIP = 11, 12
COCO_LKNEE, COCO_RKNEE = 13, 14
COCO_LANK, COCO_RANK = 15, 16


def parse_args():
    p = argparse.ArgumentParser(description="Video -> 2D (YOLO26-pose) -> 3D (KTPFormer) -> skeleton visuals -> CSV")
    p.add_argument("--video-dir", default=VIDEO_DIR, help=f"folder of .mp4 videos (default: {VIDEO_DIR})")
    p.add_argument("--output-root", default=OUTPUT_ROOT, help=f"output folder root (default: {OUTPUT_ROOT})")
    p.add_argument("--checkpoint", default=None, help="override CHECKPOINT_PATH from infer_2d_to_3d.py")
    p.add_argument("--yolo-weights", default=YOLO_WEIGHTS, help=f"YOLO26-pose weights (default: {YOLO_WEIGHTS})")
    p.add_argument("--max-gif-frames", type=int, default=MAX_FRAMES_FOR_GIF,
                    help=f"cap frames per gif, 0 = unlimited (default: {MAX_FRAMES_FOR_GIF})")
    p.add_argument("--no-gif", action="store_true", help="skip gif generation (still saves .npy/.csv and frame0.png)")
    p.add_argument("--no-csv", action="store_true", help="skip CSV export (still saves .npy)")
    p.add_argument("--class-prefix", default=None,
                    help="only process videos starting with this prefix, e.g. 'E01_' for exercise class 1 "
                         "(default: process every video in --video-dir)")
    args, _unknown = p.parse_known_args()
    return args


def coco_to_h36m17(coco_kp):
    """
    coco_kp: (T, 17, 2) COCO-order 2D keypoints
    returns: (T, 17, 2) H36M-order 2D keypoints, using the standard
    coco->h36m joint derivation (midpoints for joints COCO doesn't have:
    pelvis/hip, thorax, spine; nose used as neck/nose; head approximated
    by extending the nose away from the thorax).
    """
    T = coco_kp.shape[0]
    h36m = np.zeros((T, 17, 2), dtype=coco_kp.dtype)

    hip = (coco_kp[:, COCO_LHIP] + coco_kp[:, COCO_RHIP]) / 2.0
    thorax = (coco_kp[:, COCO_LSHO] + coco_kp[:, COCO_RSHO]) / 2.0
    spine = (hip + thorax) / 2.0
    nose = coco_kp[:, COCO_NOSE]
    head = nose + (nose - thorax) * 0.5  # extend upward past the nose, away from thorax

    h36m[:, 0] = hip
    h36m[:, 1] = coco_kp[:, COCO_RHIP]
    h36m[:, 2] = coco_kp[:, COCO_RKNEE]
    h36m[:, 3] = coco_kp[:, COCO_RANK]
    h36m[:, 4] = coco_kp[:, COCO_LHIP]
    h36m[:, 5] = coco_kp[:, COCO_LKNEE]
    h36m[:, 6] = coco_kp[:, COCO_LANK]
    h36m[:, 7] = spine
    h36m[:, 8] = thorax
    h36m[:, 9] = nose
    h36m[:, 10] = head
    h36m[:, 11] = coco_kp[:, COCO_LSHO]
    h36m[:, 12] = coco_kp[:, COCO_LELB]
    h36m[:, 13] = coco_kp[:, COCO_LWRI]
    h36m[:, 14] = coco_kp[:, COCO_RSHO]
    h36m[:, 15] = coco_kp[:, COCO_RELB]
    h36m[:, 16] = coco_kp[:, COCO_RWRI]
    return h36m


def extract_2d_keypoints(yolo_model, video_path):
    """Runs YOLO26-pose over every frame of the video, keeping only the
    highest-confidence detected person per frame. Missing detections are
    forward-filled from the last valid frame (or back-filled at the start)
    so the sequence has no gaps."""
    cap = cv2.VideoCapture(video_path)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()

    results = yolo_model(video_path, stream=True, verbose=False)
    frames_kp = []
    last_valid = None
    for r in results:
        if r.keypoints is not None and len(r.keypoints.xy) > 0:
            # if multiple people detected, take the one with highest mean confidence
            confs = r.keypoints.conf
            if confs is not None and len(confs) > 1:
                best = int(confs.mean(dim=1).argmax())
            else:
                best = 0
            kp = r.keypoints.xy[best].cpu().numpy()
            last_valid = kp
        else:
            kp = last_valid  # may still be None if no detection yet
        frames_kp.append(kp)

    # back-fill any leading None frames with the first valid detection
    first_valid = next((f for f in frames_kp if f is not None), None)
    if first_valid is None:
        raise RuntimeError(f"No person detected in any frame of {video_path}")
    frames_kp = [f if f is not None else first_valid for f in frames_kp]

    return np.stack(frames_kp, axis=0), width, height  # (T, 17, 2), width, height


def save_as_csv(arr, csv_path):
    """arr: (T, J, C) -> one row per joint per frame."""
    T, J, C = arr.shape
    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["frame", "joint", "x", "y", "z"] if C == 3 else ["frame", "joint", "x", "y"])
        for t in range(T):
            for j in range(J):
                writer.writerow([t, j] + [f"{v:.6f}" for v in arr[t, j]])


def process_one_video(model, yolo_model, skeleton_parents, video_path, out_dir,
                       make_gif, max_gif_frames, make_csv):
    os.makedirs(out_dir, exist_ok=True)

    coco_kp, width, height = extract_2d_keypoints(yolo_model, video_path)
    h36m_kp = coco_to_h36m17(coco_kp)
    np.save(os.path.join(out_dir, "input_2d_h36m.npy"), h36m_kp)

    pred_3d = inf.predict_3d(model, h36m_kp, width, height)
    np.save(os.path.join(out_dir, "output_3d.npy"), pred_3d)

    if make_csv:
        save_as_csv(h36m_kp, os.path.join(out_dir, "input_2d_h36m.csv"))
        save_as_csv(pred_3d, os.path.join(out_dir, "output_3d.csv"))

    fig = plt.figure(figsize=(6, 6))
    ax = fig.add_subplot(111, projection="3d")
    plot_skeleton(ax, pred_3d[0], skeleton_parents)
    ax.set_title("frame 0")
    fig.savefig(os.path.join(out_dir, "skeleton_frame0.png"), dpi=120)
    plt.close(fig)

    if make_gif:
        n_frames = pred_3d.shape[0]
        if max_gif_frames:
            n_frames = min(n_frames, max_gif_frames)

        fig = plt.figure(figsize=(6, 6))
        ax = fig.add_subplot(111, projection="3d")

        def update(i):
            plot_skeleton(ax, pred_3d[i], skeleton_parents)
            ax.set_title(f"frame {i}")

        anim = FuncAnimation(fig, update, frames=n_frames, interval=1000 / 25)
        anim.save(os.path.join(out_dir, "skeleton_animation.gif"), writer="pillow", fps=25)
        plt.close(fig)

    return pred_3d.shape


if __name__ == "__main__":
    args = parse_args()

    if args.checkpoint is not None:
        inf.CHECKPOINT_PATH = args.checkpoint

    print(f"Checkpoint: {inf.CHECKPOINT_PATH}")
    print("Loading KTPFormer model...")
    model = inf.load_model()
    skeleton = inf.build_h36m_17j_skeleton()
    parents = skeleton.parents()

    print(f"Loading YOLO26-pose weights: {args.yolo_weights}")
    yolo_model = YOLO(args.yolo_weights)

    video_files = sorted(f for f in os.listdir(args.video_dir) if f.lower().endswith((".mp4", ".mov", ".avi")))
    if args.class_prefix:
        before = len(video_files)
        video_files = [f for f in video_files if f.startswith(args.class_prefix)]
        print(f"Filtered by prefix '{args.class_prefix}': {before} -> {len(video_files)} video(s)")
    print(f"Found {len(video_files)} video(s) in {args.video_dir}: {video_files}")

    os.makedirs(args.output_root, exist_ok=True)
    max_gif_frames = None if args.max_gif_frames == 0 else args.max_gif_frames

    for video_file in video_files:
        video_path = os.path.join(args.video_dir, video_file)
        video_name = os.path.splitext(video_file)[0]
        out_dir = os.path.join(args.output_root, video_name)
        print(f"Processing {video_file} -> {out_dir}")
        shape = process_one_video(model, yolo_model, parents, video_path, out_dir,
                                   not args.no_gif, max_gif_frames, not args.no_csv)
        print(f"  done, output_3d shape {shape}")

    print(f"\nAll {len(video_files)} video(s) done. Results under: {args.output_root}/<video_name>/")
